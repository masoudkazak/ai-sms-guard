import logging
import uuid

logger = logging.getLogger(__name__)


def send_sms(phone: str, body: str) -> dict[str, int | str]:
    provider_message_id = str(uuid.uuid4())
    provider_status = 1
    logger.info(
        "MOCK SMS accepted provider_message_id=%s phone=%s body_len=%d provider_status=%s",
        provider_message_id,
        phone,
        len(body),
        provider_status,
    )
    return {
        "message_id": provider_message_id,
        "status": provider_status,
    }
