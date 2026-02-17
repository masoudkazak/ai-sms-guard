import os
import logging
from typing import Literal

import db as worker_db

logger = logging.getLogger(__name__)

DUPLICATE_WINDOW_SECONDS = int(os.environ.get("DUPLICATE_WINDOW_SECONDS", "300"))
MAX_RETRY_BEFORE_DLQ = int(os.environ.get("MAX_RETRY_BEFORE_DLQ", "3"))
MULTIPART_SEGMENT_THRESHOLD = int(os.environ.get("MULTIPART_SEGMENT_THRESHOLD", "2"))

RuleResult = Literal["SEND", "REVIEW", "POISON"]


def classify(
    message_id: str,
    phone: str,
    body: str,
    retry_count: int,
    last_dlr: str | None,
    segment_count: int,
) -> RuleResult:
    # Scenario 1: Retry on permanent failure -> internal cost; send to DLQ for AI decision
    if retry_count >= MAX_RETRY_BEFORE_DLQ:
        logger.info("Rule: POISON (retry_count=%s >= %s)", retry_count, MAX_RETRY_BEFORE_DLQ)
        return "POISON"
    if last_dlr in ("FAILED", "BLOCKED") and retry_count >= 1:
        logger.info("Rule: POISON (last_dlr=%s, retry_count=%s)", last_dlr, retry_count)
        return "POISON"

    # Scenario 2: Retry on timeout -> risk of duplicate after delivery; REVIEW
    if last_dlr == "TIMEOUT" and retry_count >= 1:
        logger.info("Rule: REVIEW (timeout retry message_id=%s)", message_id)
        return "REVIEW"

    # Scenario 3: Multipart unwanted / low-value high-cost -> REVIEW
    if segment_count > MULTIPART_SEGMENT_THRESHOLD:
        logger.info("Rule: REVIEW (multipart segments=%s)", segment_count)
        return "REVIEW"

    # Scenario 4: Long message without multipart flag could still be high cost
    if len(body) > 320 and segment_count >= 2:
        logger.info("Rule: REVIEW (long body + segments message_id=%s)", message_id)
        return "REVIEW"

    # Scenario 5: Duplicate SMS -> internal cost; REVIEW so AI can DROP
    duplicate_message_id, duplicate_phone_body = worker_db.get_duplicate_flags(
        message_id, phone, body, DUPLICATE_WINDOW_SECONDS
    )
    if duplicate_message_id:
        logger.info("Rule: REVIEW (duplicate message_id=%s)", message_id)
        return "REVIEW"
    if duplicate_phone_body:
        logger.info("Rule: REVIEW (duplicate phone+body in window)")
        return "REVIEW"

    return "SEND"
