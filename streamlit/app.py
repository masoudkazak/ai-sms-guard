
import os
import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
if not BACKEND_URL:
    st.error("Missing BACKEND_URL env var (example: http://backend:8000).")
    st.stop()


def fetch_stats():
    resp = requests.get(f"{BACKEND_URL}/stats", timeout=10)
    resp.raise_for_status()
    payload = resp.json() or {}
    by_status = payload.get("by_status") or {}
    ai = payload.get("ai") or {"cnt": 0, "in_tok": 0, "out_tok": 0}
    ai_today = payload.get("ai_today") or {"cnt": 0, "limit": 50, "remaining": 50, "redis_ok": True}
    return by_status, ai, ai_today


st.title("AI SMS Guard")

try:
    by_status, ai, ai_today = fetch_stats()
except Exception as e:
    st.error(f"Backend error: {e}")
    st.stop()

sent = by_status.get("SENT", 0)
blocked = by_status.get("BLOCKED", 0)
ai_calls = ai["cnt"]
in_tok = ai["in_tok"]
out_tok = ai["out_tok"]
ai_today_used = int(ai_today.get("cnt", 0))
ai_today_limit = int(ai_today.get("limit", 50))
ai_today_remaining = int(ai_today.get("remaining", max(0, ai_today_limit - ai_today_used)))
redis_ok = bool(ai_today.get("redis_ok", True))

# AI token cost defaults (based on the ranges you provided):
# - Input:  $0.10-$0.13 per 1M tokens  => $0.00010-$0.00013 per 1K tokens (default: midpoint $0.000115)
# - Output: $0.32-$0.40 per 1M tokens  => $0.00032-$0.00040 per 1K tokens (default: midpoint $0.00036)
INPUT_COST_PER_1K = float(os.environ.get("INPUT_COST_PER_1K"))
OUTPUT_COST_PER_1K = float(os.environ.get("OUTPUT_COST_PER_1K"))
USD_TO_TOMAN = float(os.environ.get("USD_TO_TOMAN"))
cost_ai_usd = (in_tok / 1000.0) * INPUT_COST_PER_1K + (out_tok / 1000.0) * OUTPUT_COST_PER_1K
cost_ai_toman = cost_ai_usd * USD_TO_TOMAN

# SMS cost saved: blocked messages we did not send (example cost per SMS)
COST_PER_SMS = float(os.environ.get("COST_PER_SMS"))
cost_sms_saved = blocked * COST_PER_SMS
net_saving = cost_sms_saved - cost_ai_toman

st.metric("SMS Sent", sent)
st.metric("SMS Blocked", blocked)
st.metric("AI Calls", ai_calls)
st.metric("AI Today", f"{ai_today_used} / {ai_today_limit}")
st.metric("AI Remaining Today", ai_today_remaining)
if not redis_ok:
    st.warning("Redis is unavailable; rate-limit metrics may be inaccurate.")
elif ai_today_remaining <= 0:
    st.warning("AI daily usage limit reached.")
st.metric("Estimated AI Cost (Toman)", f"{cost_ai_toman}")
st.metric("Saved SMS Cost (Toman)", f"{cost_sms_saved}")
st.metric("Net Savings (Toman)", f"{net_saving}")
