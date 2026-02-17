import json
import logging
import threading
from typing import Any

import pika

from rule_engine import classify
from ai_guard import call_ai_guard
from sms_sender_mock import send_sms
import db as worker_db
from env import (
    OPENROUTER_MODEL,
    RABBITMQ_DLQ,
    RABBITMQ_MAIN_QUEUE,
    RABBITMQ_URL,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _ensure_queues(channel: pika.channel.Channel) -> None:
    channel.queue_declare(queue=RABBITMQ_MAIN_QUEUE, durable=True)
    channel.queue_declare(queue=RABBITMQ_DLQ, durable=True)


def _process_main_message(body: bytes) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON, nacking")
        return
    message_id = payload.get("message_id", "")
    phone = payload.get("phone", "")
    body_text = payload.get("body", "")
    retry_count = int(payload.get("retry_count", 0))
    segment_count = int(payload.get("segment_count", 1))
    last_dlr = payload.get("last_dlr")

    result = classify(message_id, phone, body_text, retry_count, last_dlr, segment_count)

    if result == "SEND":
        dlr = send_sms(phone, body_text, message_id)
        status = "SENT" if dlr == "DELIVERED" else "PENDING"
        next_retry = retry_count if dlr == "DELIVERED" else retry_count + 1
        worker_db.update_sms_status(message_id, status, last_dlr=dlr, retry_count=next_retry)
        return

    if result == "REVIEW":
        decision_data, in_tok, out_tok = call_ai_guard(message_id, phone, body_text, retry_count, last_dlr, segment_count)
        decision = (decision_data.get("decision") or "DROP").upper()
        reason = decision_data.get("reason") or ""
        sms_row = worker_db.get_sms_by_message_id(message_id)
        sms_event_id = sms_row["id"] if sms_row else None
        worker_db.insert_ai_call(sms_event_id, OPENROUTER_MODEL, in_tok, out_tok, decision, reason)
        worker_db.update_sms_status(message_id, "IN_REVIEW")
        if decision == "RETRY":
            payload["retry_count"] = retry_count + 1
            _publish_to_main(payload)
            worker_db.update_sms_status(message_id, "PENDING", retry_count=retry_count + 1)
        else:
            worker_db.update_sms_status(message_id, "BLOCKED")
        return

    _publish_to_dlq(body)
    worker_db.update_sms_status(message_id, "IN_DLQ")
    return


def _process_dlq_message(body: bytes) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("DLQ invalid JSON")
        return
    message_id = payload.get("message_id", "")
    phone = payload.get("phone", "")
    body_text = payload.get("body", "")
    retry_count = int(payload.get("retry_count", 0))
    segment_count = int(payload.get("segment_count", 1))
    last_dlr = payload.get("last_dlr")

    decision_data, in_tok, out_tok = call_ai_guard(message_id, phone, body_text, retry_count, last_dlr, segment_count)
    decision = (decision_data.get("decision") or "DROP").upper()
    reason = decision_data.get("reason") or ""
    sms_row = worker_db.get_sms_by_message_id(message_id)
    sms_event_id = sms_row["id"] if sms_row else None
    worker_db.insert_ai_call(sms_event_id, OPENROUTER_MODEL, in_tok, out_tok, decision, reason)

    if decision == "RETRY":
        payload["retry_count"] = retry_count + 1
        _publish_to_main(payload)
        worker_db.update_sms_status(message_id, "PENDING", retry_count=retry_count + 1)
    else:
        worker_db.update_sms_status(message_id, "BLOCKED")
    return


_thread_local = threading.local()


def _get_publish_channel() -> pika.channel.Channel:
    if not getattr(_thread_local, "channel", None) or _thread_local.channel.is_closed:
        conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        _thread_local.channel = conn.channel()
        _ensure_queues(_thread_local.channel)
    return _thread_local.channel


def _publish_to_main(payload: dict[str, Any]) -> None:
    ch = _get_publish_channel()
    ch.basic_publish(
        exchange="",
        routing_key=RABBITMQ_MAIN_QUEUE,
        body=json.dumps(payload).encode(),
        properties=pika.BasicProperties(delivery_mode=2),
    )


def _publish_to_dlq(body: bytes) -> None:
    ch = _get_publish_channel()
    ch.basic_publish(
        exchange="",
        routing_key=RABBITMQ_DLQ,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2),
    )


def _run_main_consumer() -> None:
    conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    ch = conn.channel()
    _ensure_queues(ch)
    ch.basic_qos(prefetch_count=1)

    def on_message(channel, method, properties, body):
        try:
            _process_main_message(body)
            channel.basic_ack(method.delivery_tag)
        except Exception as e:
            logger.exception("Main consumer error: %s", e)
            channel.basic_nack(method.delivery_tag, requeue=False)

    ch.basic_consume(queue=RABBITMQ_MAIN_QUEUE, on_message_callback=on_message)
    logger.info("Consuming from %s", RABBITMQ_MAIN_QUEUE)
    ch.start_consuming()


def _run_dlq_consumer() -> None:
    conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    ch = conn.channel()
    _ensure_queues(ch)
    ch.basic_qos(prefetch_count=1)

    def on_message(channel, method, properties, body):
        try:
            _process_dlq_message(body)
            channel.basic_ack(method.delivery_tag)
        except Exception as e:
            logger.exception("DLQ consumer error: %s", e)
            channel.basic_nack(method.delivery_tag, requeue=False)

    ch.basic_consume(queue=RABBITMQ_DLQ, on_message_callback=on_message)
    logger.info("Consuming from %s", RABBITMQ_DLQ)
    ch.start_consuming()


def main() -> None:
    t1 = threading.Thread(target=_run_main_consumer, daemon=True)
    t2 = threading.Thread(target=_run_dlq_consumer, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


if __name__ == "__main__":
    main()
