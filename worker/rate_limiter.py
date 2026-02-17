from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import redis

logger = logging.getLogger(__name__)


_LUA_CONSUME_DAILY = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl_seconds = tonumber(ARGV[2])

local current = redis.call('INCR', key)
if current == 1 then
  redis.call('EXPIRE', key, ttl_seconds)
end

if current > limit then
  redis.call('DECR', key)
  return {0, current - 1}
end

return {1, current}
"""


@dataclass(frozen=True)
class DailyLimitResult:
    allowed: bool
    used_today: int
    remaining_today: int
    day_key: str


def _seconds_until_next_midnight(tz: ZoneInfo) -> int:
    now = datetime.now(tz=tz)
    tomorrow = (now + timedelta(days=1)).date()
    next_midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=tz)
    seconds = int((next_midnight - now).total_seconds())
    return max(1, seconds)


def _today_key(prefix: str, tz: ZoneInfo) -> str:
    today = datetime.now(tz=tz).date().isoformat()
    return f"{prefix}:{today}"


def try_consume_daily_limit(
    redis_url: str,
    *,
    key_prefix: str,
    limit: int,
    tz_name: str,
    socket_timeout_seconds: float = 1.0,
) -> DailyLimitResult:
    if limit <= 0:
        return DailyLimitResult(False, 0, 0, day_key=_today_key(key_prefix, ZoneInfo("UTC")))

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning("Invalid timezone %r; falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")

    day_key = _today_key(key_prefix, tz)
    ttl_seconds = _seconds_until_next_midnight(tz)

    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_timeout=socket_timeout_seconds,
        socket_connect_timeout=socket_timeout_seconds,
    )

    try:
        allowed, used = client.eval(_LUA_CONSUME_DAILY, 1, day_key, str(limit), str(ttl_seconds))
        allowed_bool = bool(int(allowed))
        used_int = int(used)
        remaining = max(0, limit - used_int)
        return DailyLimitResult(allowed_bool, used_int, remaining, day_key=day_key)
    except Exception as e:
        logger.exception("Redis rate limit check failed: %s", e)
        return DailyLimitResult(False, 0, 0, day_key=day_key)

