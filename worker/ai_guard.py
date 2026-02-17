import os
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL").rstrip("/")
OPENROUTER_TIMEOUT = int(os.environ.get("OPENROUTER_TIMEOUT", "15"))

SYSTEM_PROMPT = """You are an SMS cost guard. Reply only with a single JSON object, no other text.
Output format: {"decision": "DROP"|"RETRY"|"REWRITE", "reason": "short reason"}
- DROP: do not send, avoid cost (duplicate, low value, permanent failure).
- RETRY: send again (e.g. temporary timeout).
- REWRITE: suggest shortening or splitting (e.g. multipart cost)."""


def _build_user_prompt(message_id: str, phone: str, body: str, retry_count: int, last_dlr: str | None, segment_count: int) -> str:
    return (
        f"message_id={message_id} phone={phone} retry_count={retry_count} last_dlr={last_dlr or 'none'} segments={segment_count}\n"
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

    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(message_id, phone, body, retry_count, last_dlr, segment_count)},
        ],
        "max_tokens": 60,
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
            logger.info(r)
            r.raise_for_status()
            data = r.json()
            logger.info(data)
    except Exception as e:
        logger.exception("OpenRouter request failed: %s", e)
        return ({"decision": "DROP", "reason": f"AI error: {e}"}, 0, 0)

    usage = data.get("usage", {}) or {}
    input_tokens = int(usage.get("prompt_tokens", 0))
    output_tokens = int(usage.get("completion_tokens", 0))
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        decision_data = _safe_json_parse(content)
    except json.JSONDecodeError:
        logger.warning("AI returned non-JSON: %s", content[:200])
        decision_data = {"decision": "DROP", "reason": "Invalid AI response"}
    if "decision" not in decision_data:
        decision_data["decision"] = "DROP"
    if "reason" not in decision_data:
        decision_data["reason"] = "Unknown"
    return (decision_data, input_tokens, output_tokens)
