import os
import logging
import random
from typing import Literal

logger = logging.getLogger(__name__)

MOCK_DLR_OVERRIDE = os.environ.get("MOCK_DLR", "").upper() or None
if MOCK_DLR_OVERRIDE and MOCK_DLR_OVERRIDE not in ("DELIVERED", "FAILED", "BLOCKED", "TIMEOUT"):
    MOCK_DLR_OVERRIDE = None


def send_sms(phone: str, body: str, message_id: str) -> Literal["DELIVERED", "FAILED", "BLOCKED", "TIMEOUT"]:
    logger.info("MOCK SMS send message_id=%s phone=%s body_len=%d", message_id, phone, len(body))
    if MOCK_DLR_OVERRIDE:
        return MOCK_DLR_OVERRIDE

    r = random.random()
    if r < 0.85:
        return "DELIVERED"
    if r < 0.95:
        return "TIMEOUT"
    if r < 0.98:
        return "FAILED"
    return "BLOCKED"
