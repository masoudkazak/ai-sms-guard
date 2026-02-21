import json
import logging
import re
from typing import Any

import httpx

from env import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_TIMEOUT,
    REDIS_URL,
    AI_DAILY_CALL_LIMIT,
    MAX_BODY_CHARS,
    AI_GUARD_MAX_TOKENS,
)
from rate_limiter import try_consume_daily_limit

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an SMS cost guard. Reply only with a single JSON object, no other text.
Output format:
{"decision": "DROP"|"REWRITE", "reason": "short reason", "body": "shortened sms when decision=REWRITE"}
- DROP: do not send, avoid cost (duplicate, low value, permanent failure).
- REWRITE: provide a shortened SMS that preserves meaning. The "body" must be <= max_chars."""


def _build_user_prompt(message_id: str, phone: str, body: str, retry_count: int, last_dlr: str | None, segment_count: int) -> str:
    return (
        f"message_id={message_id} phone={phone} retry_count={retry_count} last_dlr={last_dlr or 'none'} "
        f"segments={segment_count} max_chars={MAX_BODY_CHARS}\n"
        f"body: {body[:500]}"
    )


def _safe_json_parse(text: str) -> dict[str, Any]:
    text = text.strip()

    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)

def _extract_partial_fields(text: str) -> dict[str, Any]:
    def _extract_string_field(name: str) -> str | None:
        match = re.search(rf"\"{name}\"\\s*:\\s*\"", text)
        if not match:
            return None
        start = match.end()
        i = start
        escaped = False
        while i < len(text):
            ch = text[i]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "\"":
                return text[start:i]
            i += 1
        return text[start:] if start < len(text) else None

    result: dict[str, Any] = {}
    for field in ("decision", "reason", "body"):
        raw = _extract_string_field(field)
        if raw is None:
            continue
        try:
            value = json.loads(f"\"{raw}\"")
        except json.JSONDecodeError:
            value = raw.rstrip("\\")
        result[field] = value
    return result


def call_ai_guard(
    message_id: str,
    phone: str,
    body: str,
    retry_count: int = 0,
    last_dlr: str | None = None,
    segment_count: int = 1,
) -> tuple[dict[str, Any], int, int]:
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set; returning default DROP")
        return ({"decision": "DROP", "reason": "AI not configured"}, 0, 0)

    limit_result = try_consume_daily_limit(
        REDIS_URL,
        key_prefix="ai_guard_calls",
        limit=AI_DAILY_CALL_LIMIT,
        tz_name="UTC",
    )
    if not limit_result.allowed:
        return (
            {
                "decision": "DROP",
                "reason": "AI daily usage limit reached.",
                "rate_limited": True,
                "used_today": limit_result.used_today,
                "limit": AI_DAILY_CALL_LIMIT,
            },
            0,
            0,
        )

    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(message_id, phone, body, retry_count, last_dlr, segment_count)},
        ],
        "max_tokens": AI_GUARD_MAX_TOKENS,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    logger.info(payload)
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=OPENROUTER_TIMEOUT) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            logger.info(data)
    except Exception as e:
        logger.exception("OpenRouter request failed: %s", e)
        return ({"decision": "DROP", "reason": f"AI error: {e}"}, 0, 0)

    usage = data.get("usage", {}) or {}
    input_tokens = int(usage.get("prompt_tokens", 0))
    output_tokens = int(usage.get("completion_tokens", 0))
    choice = (data.get("choices") or [{}])[0]
    finish_reason = choice.get("finish_reason")
    content = (choice.get("message") or {}).get("content", "{}")
    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        decision_data = _safe_json_parse(content)
    except json.JSONDecodeError:
        logger.warning("AI returned non-JSON: %s", content[:200])
        decision_data = _extract_partial_fields(content)
        if not decision_data:
            decision_data = {"decision": "DROP", "reason": "Invalid AI response"}
    if finish_reason == "length" and decision_data.get("decision") == "REWRITE" and not decision_data.get("body"):
        decision_data = {"decision": "DROP", "reason": "AI response truncated"}
    if "decision" not in decision_data:
        decision_data["decision"] = "DROP"
    if "reason" not in decision_data:
        decision_data["reason"] = "Unknown"
    return (decision_data, input_tokens, output_tokens)
