import json
import os
import uuid
import asyncio
from contextlib import asynccontextmanager

import pika
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, Field

from db import get_db, engine
from models import SmsEvent, SmsStatus


RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
RABBITMQ_MAIN_QUEUE = os.environ.get("RABBITMQ_MAIN_QUEUE", "sms_main")
HOST = os.environ.get("BACKEND_HOST", "0.0.0.0")
PORT = int(os.environ.get("BACKEND_PORT", "8000"))


class SmsRequest(BaseModel):
    phone: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)


def _get_connection():
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def _publish_to_main_queue(body: bytes) -> None:
    conn = _get_connection()
    ch = conn.channel()
    ch.queue_declare(queue=RABBITMQ_MAIN_QUEUE, durable=True)
    ch.basic_publish(exchange="", routing_key=RABBITMQ_MAIN_QUEUE, body=body)
    ch.close()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Smart Rabbit Backend", lifespan=lifespan)


@app.get("/stats")
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
    return {"by_status": by_status, "ai": dict(ai)}


@app.post("/sms")
async def send_sms(request: SmsRequest, db: AsyncSession = Depends(get_db)):
    message_id = str(uuid.uuid4())
    segment_count = max(1, (len(request.body) + 159) // 160)

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

