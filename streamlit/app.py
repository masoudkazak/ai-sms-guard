
import os
import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL").rstrip("/")


def fetch_stats():
    resp = requests.get(f"{BACKEND_URL}/stats", timeout=10)
    resp.raise_for_status()
    payload = resp.json() or {}
    by_status = payload.get("by_status") or {}
    ai = payload.get("ai") or {"cnt": 0, "in_tok": 0, "out_tok": 0}
    return by_status, ai


st.title("Smart Rabbit — Cost Dashboard")

try:
    by_status, ai = fetch_stats()
except Exception as e:
    st.error(f"Backend error: {e}")
    st.stop()

sent = by_status.get("SENT", 0)
blocked = by_status.get("BLOCKED", 0)
ai_calls = ai["cnt"]
in_tok = ai["in_tok"]
out_tok = ai["out_tok"]

# AI token cost defaults (based on the ranges you provided):
# - Input:  $0.10–$0.13 per 1M tokens  => $0.00010–$0.00013 per 1K tokens (default: midpoint $0.000115)
# - Output: $0.32–$0.40 per 1M tokens  => $0.00032–$0.00040 per 1K tokens (default: midpoint $0.00036)
INPUT_COST_PER_1K = float(os.environ.get("INPUT_COST_PER_1K"))
OUTPUT_COST_PER_1K = float(os.environ.get("OUTPUT_COST_PER_1K"))
USD_TO_TOMAN = float(os.environ.get("USD_TO_TOMAN"))
cost_ai_usd = (in_tok / 1000.0) * INPUT_COST_PER_1K + (out_tok / 1000.0) * OUTPUT_COST_PER_1K
cost_ai_toman = cost_ai_usd * USD_TO_TOMAN

# SMS cost saved: blocked messages we did not send (example cost per SMS)
COST_PER_SMS = float(os.environ.get("COST_PER_SMS"))
cost_sms_saved = blocked * COST_PER_SMS
net_saving = cost_sms_saved - cost_ai_toman

st.metric("SMS ارسال شده", sent)
st.metric("SMS بلاک شده", blocked)
st.metric("تعداد AI Call", ai_calls)
st.metric("هزینه تخمینی AI (تومان)", f"{cost_ai_toman}")
st.metric("هزینه SMS صرفه‌جویی‌شده (تومان)", f"{cost_sms_saved}")
st.metric("صرفه‌جویی خالص (تومان)", f"{net_saving}")
