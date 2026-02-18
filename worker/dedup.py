from __future__ import annotations

import hashlib
import logging
import re
import unicodedata

import redis

logger = logging.getLogger(__name__)


_LUA_PHONE_BODY_WINDOW = """
local pb_key = KEYS[1]
local ttl_seconds = tonumber(ARGV[1])
local message_id = ARGV[2]

local existing = redis.call('GET', pb_key)

if existing == false then
  redis.call('SET', pb_key, message_id, 'EX', ttl_seconds)
  return 0
end

if existing == message_id then
  redis.call('EXPIRE', pb_key, ttl_seconds)
  return 0
end

redis.call('EXPIRE', pb_key, ttl_seconds)
return 1
"""


def _normalize_phone(phone: str) -> str:
    return phone.strip()


_WS_RE = re.compile(r"\s+", flags=re.UNICODE)


def _normalize_body(body: str) -> str:
    normalized = unicodedata.normalize("NFKC", body)
    normalized = _WS_RE.sub(" ", normalized).strip()
    return normalized


def _phone_body_fingerprint(phone: str, body: str) -> str:
    phone_norm = _normalize_phone(phone)
    body_norm = _normalize_body(body)
    payload = f"{phone_norm}\n{body_norm}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def get_duplicate_flags(
    redis_url: str,
    *,
    message_id: str,
    phone: str,
    body: str,
    window_seconds: int,
    key_prefix: str = "dedup:sms",
    socket_timeout_seconds: float = 1.0,
) -> tuple[bool, bool]:
    if window_seconds <= 0:
        return (False, False)

    mid_key = f"{key_prefix}:mid:{message_id}"
    pb_key = f"{key_prefix}:pb:{_phone_body_fingerprint(phone, body)}"

    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_timeout=socket_timeout_seconds,
        socket_connect_timeout=socket_timeout_seconds,
    )

    try:
        duplicate_message_id = bool(int(client.exists(mid_key)))
        duplicate_phone_body = bool(int(client.eval(_LUA_PHONE_BODY_WINDOW, 1, pb_key, str(window_seconds), message_id)))
        return (duplicate_message_id, duplicate_phone_body)
    except Exception as e:
        logger.exception("Redis dedup check failed (mid=%s): %s", message_id, e)
        return (False, False)


def mark_message_id(
    redis_url: str,
    *,
    message_id: str,
    ttl_seconds: int,
    key_prefix: str = "dedup:sms",
    socket_timeout_seconds: float = 1.0,
) -> None:
    if ttl_seconds <= 0:
        return

    mid_key = f"{key_prefix}:mid:{message_id}"
    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_timeout=socket_timeout_seconds,
        socket_connect_timeout=socket_timeout_seconds,
    )
    try:
        client.set(mid_key, "1", ex=ttl_seconds)
    except Exception as e:
        logger.exception("Redis dedup mark_message_id failed (mid=%s): %s", message_id, e)
