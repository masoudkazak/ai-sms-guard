import logging
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from env import DATABASE_URL

logger = logging.getLogger(__name__)


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_sms_by_id(sms_event_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, message_id, phone, body, rewritten_body, status, retry_count, segment_count, last_dlr, provider_status
                FROM sms_events
                WHERE id = %s
                """,
                (sms_event_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_sms_by_message_id(message_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, message_id, phone, body, rewritten_body, status, retry_count, segment_count, last_dlr, provider_status
                FROM sms_events
                WHERE message_id = %s
                """,
                (message_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def update_sms_status_by_id(
    sms_event_id: int,
    status: str,
    last_dlr: str | None = None,
    retry_count: int | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if retry_count is not None:
                cur.execute(
                    """
                    UPDATE sms_events
                    SET status = %s,
                        last_dlr = COALESCE(%s, last_dlr),
                        retry_count = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (status, last_dlr, retry_count, sms_event_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE sms_events
                    SET status = %s,
                        last_dlr = COALESCE(%s, last_dlr),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (status, last_dlr, sms_event_id),
                )


def update_sms_status(message_id: str, status: str, last_dlr: str | None = None, retry_count: int | None = None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if retry_count is not None:
                cur.execute(
                    """
                    UPDATE sms_events
                    SET status = %s,
                        last_dlr = COALESCE(%s, last_dlr),
                        retry_count = %s,
                        updated_at = NOW()
                    WHERE message_id = %s
                    """,
                    (status, last_dlr, retry_count, message_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE sms_events
                    SET status = %s,
                        last_dlr = COALESCE(%s, last_dlr),
                        updated_at = NOW()
                    WHERE message_id = %s
                    """,
                    (status, last_dlr, message_id),
                )


def assign_provider_message(sms_event_id: int, message_id: str, provider_status_code: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sms_events
                SET message_id = %s,
                    provider_status = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (message_id, provider_status_code, sms_event_id),
            )


def update_provider_status_by_message_id(message_id: str, provider_status_code: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sms_events
                SET provider_status = %s,
                    updated_at = NOW()
                WHERE message_id = %s
                """,
                (provider_status_code, message_id),
            )


def update_sms_rewritten_body_by_id(sms_event_id: int, rewritten_body: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sms_events SET rewritten_body = %s, updated_at = NOW() WHERE id = %s",
                (rewritten_body, sms_event_id),
            )


def update_sms_segment_count_by_id(sms_event_id: int, segment_count: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sms_events SET segment_count = %s, updated_at = NOW() WHERE id = %s",
                (segment_count, sms_event_id),
            )


def insert_ai_call(sms_event_id: int | None, model: str, input_tokens: int, output_tokens: int, decision: str | None, reason: str | None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ai_calls (sms_event_id, model, input_tokens, output_tokens, decision, reason, created_at) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                (sms_event_id, model, input_tokens, output_tokens, decision, reason),
            )


def exists_sent_or_review(message_id: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM sms_events WHERE message_id = %s AND status IN ('SENT', 'IN_REVIEW', 'IN_DLQ') LIMIT 1",
                (message_id,),
            )
            return cur.fetchone() is not None


def exists_duplicate_phone_body(phone: str, body: str, message_id: str, window_seconds: int) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM sms_events WHERE phone = %s AND body = %s AND COALESCE(message_id, '') != %s AND created_at > NOW() - INTERVAL '1 second' * %s LIMIT 1",
                (phone, body, message_id, window_seconds),
            )
            return cur.fetchone() is not None


def get_duplicate_flags(message_id: str, phone: str, body: str, window_seconds: int) -> tuple[bool, bool]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    EXISTS(
                        SELECT 1
                        FROM sms_events
                        WHERE message_id = %s
                          AND status IN ('SENT', 'IN_REVIEW', 'IN_DLQ')
                        LIMIT 1
                    ) AS duplicate_message_id,
                    EXISTS(
                        SELECT 1
                        FROM sms_events
                        WHERE phone = %s
                          AND body = %s
                          AND COALESCE(message_id, '') != %s
                          AND created_at > NOW() - INTERVAL '1 second' * %s
                        LIMIT 1
                    ) AS duplicate_phone_body
                """,
                (message_id, phone, body, message_id, window_seconds),
            )
            row = cur.fetchone() or {}
            return (bool(row.get("duplicate_message_id")), bool(row.get("duplicate_phone_body")))


def is_duplicate(message_id: str, phone: str, body: str, window_seconds: int) -> bool:
    duplicate_message_id, duplicate_phone_body = get_duplicate_flags(message_id, phone, body, window_seconds)
    return duplicate_message_id or duplicate_phone_body
