import json
import logging
import random

import db as worker_db

import dedup
from ai_guard import call_ai_guard
from env import (
    DUPLICATE_WINDOW_SECONDS,
    MAX_RETRY_BEFORE_DLQ,
    MOCK_TIMEOUT_RETRY_PROB,
    OPENROUTER_MODEL,
    REDIS_URL,
)
from publisher import _publish_to_dlq, _publish_to_main
from rule_engine import classify
from sms_sender_mock import send_sms

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _process_main_message(body: bytes) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON, nacking")
        return

    sms_event_id = int(payload.get("sms_event_id", 0) or 0)
    if sms_event_id <= 0:
        logger.warning("Missing sms_event_id in payload")
        return

    sms_row = worker_db.get_sms_by_id(sms_event_id)
    if not sms_row:
        logger.warning("sms_event not found id=%s", sms_event_id)
        return

    message_id = sms_row.get("message_id") or ""
    processing_id = message_id or f"event:{sms_event_id}"
    phone = payload.get("phone") or sms_row.get("phone") or ""
    body_text = payload.get("body") or sms_row.get("rewritten_body") or sms_row.get("body") or ""
    retry_count = int(payload.get("retry_count", sms_row.get("retry_count") or 0))
    segment_count = int(payload.get("segment_count", sms_row.get("segment_count") or 1))
    last_dlr = payload.get("last_dlr", sms_row.get("last_dlr"))

    result = classify(processing_id, phone, body_text, retry_count, last_dlr, segment_count)

    if result == "SEND":
        provider_response = send_sms(phone, body_text)
        provider_message_id = str(provider_response.get("message_id") or "")
        provider_status = int(provider_response.get("status", 1) or 1)
        if not provider_message_id:
            logger.warning("Provider did not return message_id for sms_event_id=%s", sms_event_id)
            worker_db.update_sms_status_by_id(sms_event_id, "PENDING", retry_count=retry_count + 1)
            return

        worker_db.assign_provider_message(sms_event_id, provider_message_id, provider_status)

        # Rare timeout simulation for realistic retry testing.
        if retry_count < MAX_RETRY_BEFORE_DLQ and random.random() < MOCK_TIMEOUT_RETRY_PROB:
            payload["retry_count"] = retry_count + 1
            payload["last_dlr"] = "TIMEOUT"
            _publish_to_main(payload)
            worker_db.update_sms_status_by_id(
                sms_event_id,
                "PENDING",
                last_dlr="TIMEOUT",
                retry_count=retry_count + 1,
            )
            logger.info(
                "Injected TIMEOUT for retry test sms_event_id=%s message_id=%s retry_count=%s",
                sms_event_id,
                provider_message_id,
                retry_count + 1,
            )
            return

        worker_db.update_sms_status_by_id(sms_event_id, "SENT", retry_count=retry_count)
        dedup.mark_message_id(REDIS_URL, message_id=provider_message_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
        return

    if result == "DROP":
        worker_db.update_sms_status_by_id(sms_event_id, "BLOCKED")
        dedup.mark_message_id(REDIS_URL, message_id=processing_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
        return

    if result == "REVIEW":
        decision_data, in_tok, out_tok = call_ai_guard(processing_id, phone, body_text, retry_count, last_dlr, segment_count)
        decision = (decision_data.get("decision") or "DROP").upper()
        reason = decision_data.get("reason") or ""
        worker_db.insert_ai_call(sms_event_id, OPENROUTER_MODEL, in_tok, out_tok, decision, reason)
        if decision_data.get("rate_limited"):
            worker_db.update_sms_status_by_id(sms_event_id, "BLOCKED")
            dedup.mark_message_id(REDIS_URL, message_id=processing_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
            return

        worker_db.update_sms_status_by_id(sms_event_id, "IN_REVIEW")
        if decision == "REWRITE":
            rewritten_body = (decision_data.get("body") or "").strip()
            if not rewritten_body:
                worker_db.update_sms_status_by_id(sms_event_id, "BLOCKED")
                dedup.mark_message_id(REDIS_URL, message_id=processing_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
                return

            worker_db.update_sms_rewritten_body_by_id(sms_event_id, rewritten_body)
            worker_db.update_sms_segment_count_by_id(sms_event_id, 1)
            payload["body"] = rewritten_body
            payload["segment_count"] = 1
            _publish_to_main(payload)
            worker_db.update_sms_status_by_id(sms_event_id, "PENDING", retry_count=retry_count)
        else:
            worker_db.update_sms_status_by_id(sms_event_id, "BLOCKED")
            dedup.mark_message_id(REDIS_URL, message_id=processing_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)
        return

    _publish_to_dlq(body)
    worker_db.update_sms_status_by_id(sms_event_id, "IN_DLQ")
    dedup.mark_message_id(REDIS_URL, message_id=processing_id, ttl_seconds=DUPLICATE_WINDOW_SECONDS)


def _process_dlq_message(body: bytes) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("DLQ invalid JSON")
        return

    sms_event_id = int(payload.get("sms_event_id", 0) or 0)
    if sms_event_id <= 0:
        logger.warning("DLQ message missing sms_event_id")
        return

    # DLQ is a quarantine sink. We intentionally do not call AI from DLQ to avoid extra costs.
    worker_db.update_sms_status_by_id(sms_event_id, "BLOCKED")
    dedup.mark_message_id(REDIS_URL, message_id=f"event:{sms_event_id}", ttl_seconds=DUPLICATE_WINDOW_SECONDS)
