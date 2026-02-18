import json
import logging
import db as worker_db

import dedup
from rule_engine import classify
from ai_guard import call_ai_guard
from sms_sender_mock import send_sms
from env import DUPLICATE_WINDOW_SECONDS, OPENROUTER_MODEL, REDIS_URL, MAX_RETRY_BEFORE_DLQ
from publisher import _publish_to_dlq, _publish_to_main


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        if dlr == "DELIVERED":
            dedup.mark_message_id(REDIS_URL, message_id=message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
        return

    if result == "DROP":
        worker_db.update_sms_status(message_id, "BLOCKED")
        dedup.mark_message_id(REDIS_URL, message_id=message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
        return

    if result == "REVIEW":
        # Deterministic retry for TIMEOUT before involving AI
        if last_dlr == "TIMEOUT" and retry_count < MAX_RETRY_BEFORE_DLQ:
            payload["retry_count"] = retry_count + 1
            _publish_to_main(payload)
            worker_db.update_sms_status(message_id, "PENDING", retry_count=retry_count + 1)
            return

        decision_data, in_tok, out_tok = call_ai_guard(message_id, phone, body_text, retry_count, last_dlr, segment_count)
        decision = (decision_data.get("decision") or "DROP").upper()
        reason = decision_data.get("reason") or ""
        sms_row = worker_db.get_sms_by_message_id(message_id)
        sms_event_id = sms_row["id"] if sms_row else None
        worker_db.insert_ai_call(sms_event_id, OPENROUTER_MODEL, in_tok, out_tok, decision, reason)
        if decision_data.get("rate_limited"):
            worker_db.update_sms_status(message_id, "BLOCKED")
            dedup.mark_message_id(REDIS_URL, message_id=message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
            return
        worker_db.update_sms_status(message_id, "IN_REVIEW")
        if decision == "REWRITE":
            rewritten_body = (decision_data.get("body") or "").strip()
            if not rewritten_body:
                worker_db.update_sms_status(message_id, "BLOCKED")
                dedup.mark_message_id(REDIS_URL, message_id=message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
                return
            worker_db.update_sms_rewritten_body(message_id, rewritten_body)
            worker_db.update_sms_segment_count(message_id, 1)
            payload["body"] = rewritten_body
            payload["segment_count"] = 1
            _publish_to_main(payload)
            worker_db.update_sms_status(message_id, "PENDING", retry_count=retry_count)
        else:
            worker_db.update_sms_status(message_id, "BLOCKED")
            dedup.mark_message_id(REDIS_URL, message_id=message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
        return

    _publish_to_dlq(body)
    worker_db.update_sms_status(message_id, "IN_DLQ")
    dedup.mark_message_id(REDIS_URL, message_id=message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
    return


def _process_dlq_message(body: bytes) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("DLQ invalid JSON")
        return
    message_id = payload.get("message_id", "")

    # DLQ is a quarantine sink. We intentionally do not call AI from DLQ to avoid extra costs.
    worker_db.update_sms_status(message_id, "BLOCKED")
    dedup.mark_message_id(REDIS_URL, message_id=message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
    return
