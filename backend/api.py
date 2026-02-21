import asyncio
import json
import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db import get_db
from models import SmsEvent, SmsStatus
from predictor import predict_sms_delivery_probability
from publisher import _publish_to_main_queue
from schemas import DeliveryPredictionResponse, SmsRequest, normalize_phone

router = APIRouter()
settings = get_settings()
_redis_client = None

_PROVIDER_STATUS_TEXT = {
    1: "Queued for sending",
    2: "Scheduled (send at a specified time)",
    4: "Sent to carrier",
    5: "Sent to carrier",
    6: "Failed to send",
    10: "Delivered",
    11: "Undelivered",
    13: "Cancelled/failed with refund",
    14: "Blocked (recipient opted out)",
    100: "Invalid message ID",
}
_FINAL_PROVIDER_CODES = {6, 10, 11, 13, 14, 100}
_NEXT_PROVIDER_STATUS_POOL = (
    10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
    11, 11, 11, 11,
    6, 6, 6,
    13,
    14,
)


def _get_redis():
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        _redis_client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
    return _redis_client


def _ai_daily_key() -> str:
    day = datetime.now(tz=ZoneInfo("UTC")).date().isoformat()
    return f"ai_guard_calls:{day}"


def _pick_next_status_from_queue() -> int:
    return random.choice(_NEXT_PROVIDER_STATUS_POOL)


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("SELECT status, COUNT(*)::int AS cnt FROM sms_events GROUP BY status"))
    rows = res.mappings().all()
    by_status = {r["status"]: r["cnt"] for r in rows}

    res = await db.execute(
        text(
            "SELECT COUNT(*)::int AS cnt, COALESCE(SUM(input_tokens), 0)::bigint AS in_tok, COALESCE(SUM(output_tokens), 0)::bigint AS out_tok FROM ai_calls"
        )
    )
    ai = res.mappings().first() or {"cnt": 0, "in_tok": 0, "out_tok": 0}

    ai_daily_limit = int(os.environ.get("AI_DAILY_CALL_LIMIT", "50"))
    ai_today_used = 0
    redis_ok = True
    try:
        r = _get_redis()
        raw = r.get(_ai_daily_key())
        ai_today_used = int(raw or 0)
    except Exception:
        redis_ok = False

    ai_today_remaining = max(0, ai_daily_limit - ai_today_used)

    return {
        "by_status": by_status,
        "ai": dict(ai),
        "ai_today": {
            "cnt": ai_today_used,
            "limit": ai_daily_limit,
            "remaining": ai_today_remaining,
            "redis_ok": redis_ok,
        },
    }


@router.post("/sms")
async def send_sms(request: SmsRequest, db: AsyncSession = Depends(get_db)):
    segment_count = max(1, (len(request.body) + (settings.MAX_BODY_CHARS - 1)) // settings.MAX_BODY_CHARS)

    event = SmsEvent(
        message_id=None,
        phone=request.phone,
        body=request.body,
        status=SmsStatus.PENDING.value,
        retry_count=0,
        segment_count=segment_count,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    payload = {
        "sms_event_id": event.id,
        "phone": request.phone,
        "body": request.body,
        "retry_count": 0,
        "segment_count": segment_count,
        "last_dlr": None,
    }
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _publish_to_main_queue(json.dumps(payload).encode()))
    return {"request_id": event.id, "status": "queued"}


@router.get("/sms/predict-delivery", response_model=DeliveryPredictionResponse)
async def predict_delivery(
    phone: str = Query(..., min_length=10, max_length=16, description="Phone number"),
    hour: int = Query(..., ge=0, le=24, description="Hour in UTC, 0..24 (24 maps to 0)"),
    db: AsyncSession = Depends(get_db),
):
    try:
        normalized_phone = normalize_phone(phone)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    prediction = await predict_sms_delivery_probability(db=db, phone=normalized_phone, hour=hour)
    return prediction


@router.get("/sms/status")
async def get_sms_provider_status(message_id: str = Query(..., min_length=1), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        text(
            """
            SELECT id, message_id, status, provider_status
            FROM sms_events
            WHERE message_id = :message_id
            LIMIT 1
            """
        ),
        {"message_id": message_id},
    )
    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="message_id not found")

    current_code = int(row.get("provider_status") or 1)
    resolved_code = current_code

    if current_code == 1:
        resolved_code = _pick_next_status_from_queue()

    if resolved_code != current_code:
        await db.execute(
            text("UPDATE sms_events SET provider_status = :code, updated_at = NOW() WHERE id = :id"),
            {"code": resolved_code, "id": row["id"]},
        )
        await db.commit()

    return {
        "message_id": message_id,
        "provider_status": {
            "code": resolved_code,
            "text": _PROVIDER_STATUS_TEXT.get(resolved_code, "Unknown status"),
            "final": resolved_code in _FINAL_PROVIDER_CODES,
        },
        "pipeline_status": row["status"],
    }
