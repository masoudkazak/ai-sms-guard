import logging
from typing import Literal

import dedup
from env import (
    DUPLICATE_WINDOW_SECONDS,
    MAX_RETRY_BEFORE_DLQ,
    MULTIPART_SEGMENT_THRESHOLD,
    REDIS_URL,
    MAX_BODY_CHARS,
)

logger = logging.getLogger(__name__)

RuleResult = Literal["SEND", "REVIEW", "POISON", "DROP"]


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
    if len(body) > MAX_BODY_CHARS and segment_count >= 2:
        logger.info("Rule: REVIEW (long body + segments message_id=%s)", message_id)
        return "REVIEW"

    # Scenario 5: Duplicate SMS -> internal cost; DROP
    duplicate_message_id, duplicate_phone_body = dedup.get_duplicate_flags(
        REDIS_URL,
        message_id=message_id,
        phone=phone,
        body=body,
        window_seconds=DUPLICATE_WINDOW_SECONDS,
    )
    if duplicate_message_id:
        logger.info("Rule: DROP (duplicate message_id=%s)", message_id)
        return "DROP"
    if duplicate_phone_body:
        logger.info("Rule: DROP (duplicate phone+body in window)")
        return "DROP"

    return "SEND"
