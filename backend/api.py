import json
import uuid
import asyncio
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

import redis

from db import get_db
from models import SmsEvent, SmsStatus
from publisher import _publish_to_main_queue
from config import get_settings

router = APIRouter()
settings = get_settings()
_redis_client = None


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


class SmsRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=32)
    body: str = Field(..., min_length=1)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        phone = (v or "").strip()
        if not phone:
            raise ValueError("phone is required")

        # Allow separators commonly pasted by users, but store a normalized value.
        phone = re.sub(r"[ \-\(\)]", "", phone)
        if phone.startswith("00"):
            phone = "+" + phone[2:]

        if phone.startswith("+"):
            digits = phone[1:]
            if not digits.isdigit():
                raise ValueError("phone must contain only digits (and an optional leading '+')")
            if not (10 <= len(digits) <= 15):
                raise ValueError("phone length must be 10..15 digits for E.164")
            return "+" + digits

        if not phone.isdigit():
            raise ValueError("phone must contain only digits (and an optional leading '+')")
        if not (10 <= len(phone) <= 15):
            raise ValueError("phone length must be 10..15 digits")
        return phone


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
    message_id = str(uuid.uuid4())
    segment_count = max(1, (len(request.body) + (settings.MAX_BODY_CHARS - 1)) // settings.MAX_BODY_CHARS)

    event = SmsEvent(
        message_id=message_id,
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
        "message_id": message_id,
        "phone": request.phone,
        "body": request.body,
        "retry_count": 0,
        "segment_count": segment_count,
        "last_dlr": None,
    }
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _publish_to_main_queue(json.dumps(payload).encode()))
    return {"message_id": message_id, "status": "queued"}
