import json
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings

settings = get_settings()

_SUCCESS_CODES = (10,)
_FAILURE_CODES = (6, 11, 13, 14, 100)
_FINAL_CODES_SQL = ",".join(str(c) for c in (*_SUCCESS_CODES, *_FAILURE_CODES))
_SUCCESS_CODES_SQL = ",".join(str(c) for c in _SUCCESS_CODES)

_TIME_WINDOWS = (
    {"key": "00-04", "label": "نیمه‌شب", "start": 0, "end": 4},
    {"key": "04-08", "label": "صبح زود", "start": 4, "end": 8},
    {"key": "08-12", "label": "صبح کاری", "start": 8, "end": 12},
    {"key": "12-15", "label": "ظهر", "start": 12, "end": 15},
    {"key": "15-19", "label": "عصر", "start": 15, "end": 19},
    {"key": "19-24", "label": "شب", "start": 19, "end": 24},
)

_LLM_SYSTEM_PROMPT = (
    "You are a delivery predictor for SMS.\n"
    "Use only the given numeric data.\n"
    "Return only a JSON object with this exact schema:\n"
    '{"probability":0.0,"best_window":"00-04","note":"short text"}\n'
    "Rules:\n"
    "- probability must be between 0 and 1\n"
    "- best_window must be one of: 00-04, 04-08, 08-12, 12-15, 15-19, 19-24\n"
    "- no extra keys, no markdown, no extra text"
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_hour(hour: int) -> int:
    return 0 if hour == 24 else hour


def _compute_rate(success_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0.5
    return _clamp01(success_count / total_count)


def _window_for_hour(hour: int) -> dict[str, Any]:
    for window in _TIME_WINDOWS:
        if window["start"] <= hour < window["end"]:
            return window
    return _TIME_WINDOWS[0]


async def _hourly_profile(db: AsyncSession, phone: str) -> dict[int, dict[str, int]]:
    sql = (
        "SELECT "
        "EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC')::int AS hour, "
        f"COUNT(*) FILTER (WHERE provider_status IN ({_SUCCESS_CODES_SQL}))::int AS success_count, "
        "COUNT(*)::int AS total_count "
        "FROM sms_events "
        f"WHERE provider_status IN ({_FINAL_CODES_SQL}) "
        "AND phone = :phone "
        "GROUP BY 1"
    )
    rows = (await db.execute(text(sql), {"phone": phone})).mappings().all()
    profile: dict[int, dict[str, int]] = {}
    for row in rows:
        profile[int(row["hour"])] = {
            "success_count": int(row["success_count"] or 0),
            "total_count": int(row["total_count"] or 0),
        }
    return profile


def _build_window_stats(profile: dict[int, dict[str, int]], min_samples: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for window in _TIME_WINDOWS:
        success_count = 0
        total_count = 0
        for hour in range(window["start"], window["end"]):
            bucket = profile.get(hour)
            if not bucket:
                continue
            success_count += bucket["success_count"]
            total_count += bucket["total_count"]

        rate = _compute_rate(success_count, total_count)
        low_data = total_count < min_samples
        items.append(
            {
                "window": window["key"],
                "label": window["label"],
                "success_count": success_count,
                "total_count": total_count,
                "rate": round(rate, 4),
                "status": "اطلاعات کم است" if low_data else "ok",
                "low_data": low_data,
            }
        )
    return items


def _best_window_by_stats(window_stats: list[dict[str, Any]], requested_window: str) -> str:
    valid = [w for w in window_stats if not w["low_data"]]
    if not valid:
        return requested_window
    best = max(valid, key=lambda x: x["rate"])
    return str(best["window"])


def _build_llm_payload(requested_hour: int, requested_window: str, window_stats: list[dict[str, Any]]) -> str:
    payload = {
        "requested_hour": requested_hour,
        "requested_window": requested_window,
        "windows": [
            {
                "window": item["window"],
                "success_count": item["success_count"],
                "total_count": item["total_count"],
                "rate": item["rate"],
                "low_data": 1 if item["low_data"] else 0,
            }
            for item in window_stats
        ],
    }
    return json.dumps(payload, separators=(",", ":"))


async def _ask_ai(requested_hour: int, requested_window: str, window_stats: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not settings.OPENROUTER_API_KEY or not settings.OPENROUTER_MODEL:
        return None

    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": _build_llm_payload(requested_hour, requested_window, window_stats)},
        ],
        "temperature": 0,
        "max_tokens": 120,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.OPENROUTER_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    try:
        parsed = json.loads(content)
    except Exception:
        return None

    probability = parsed.get("probability")
    best_window = parsed.get("best_window")
    note = parsed.get("note")
    if not isinstance(probability, (int, float)):
        return None
    if not isinstance(best_window, str):
        return None
    if best_window not in {w["key"] for w in _TIME_WINDOWS}:
        return None
    if not isinstance(note, str):
        note = "ai_estimated"
    return {
        "probability": round(_clamp01(float(probability)), 4),
        "best_window": best_window,
        "note": note.strip() or "ai_estimated",
    }


async def predict_sms_delivery_probability(db: AsyncSession, phone: str, hour: int) -> dict[str, Any]:
    requested_hour = _normalize_hour(hour)
    min_samples = max(1, settings.PRED_MIN_PHONE_SAMPLES)
    requested_window_meta = _window_for_hour(requested_hour)
    requested_window = str(requested_window_meta["key"])

    profile = await _hourly_profile(db, phone)
    window_stats = _build_window_stats(profile, min_samples)
    by_window = {w["window"]: w for w in window_stats}
    current_window = by_window[requested_window]
    requested_low_data = bool(current_window["low_data"])

    ai_result = await _ask_ai(requested_hour, requested_window, window_stats)
    if ai_result:
        probability = ai_result["probability"]
        best_window = ai_result["best_window"]
        note = ai_result["note"]
        source = "ai_window_analysis"
    else:
        probability = 1.0 if requested_low_data else float(current_window["rate"])
        best_window = _best_window_by_stats(window_stats, requested_window)
        note = "اطلاعات کم است" if requested_low_data else "statistical_estimate"
        source = "statistical_fallback"

    if requested_low_data and "اطلاعات کم است" not in note:
        note = f"{note} | اطلاعات کم است"

    return {
        "probability": round(_clamp01(probability), 4),
        "source": source,
        "note": note,
        "hour": requested_hour,
        "best_window": best_window,
    }
