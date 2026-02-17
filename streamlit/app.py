
import os
import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000").rstrip("/")


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

# Rough cost: e.g. $0.002/1K input, $0.002/1K output (example; configurable)
INPUT_COST_PER_1K = float(os.environ.get("INPUT_COST_PER_1K", "0.002"))
OUTPUT_COST_PER_1K = float(os.environ.get("OUTPUT_COST_PER_1K", "0.002"))
cost_ai = (in_tok / 1000.0) * INPUT_COST_PER_1K + (out_tok / 1000.0) * OUTPUT_COST_PER_1K

# SMS cost saved: blocked messages we did not send (example cost per SMS)
COST_PER_SMS = float(os.environ.get("COST_PER_SMS", "0.01"))
cost_sms_saved = blocked * COST_PER_SMS

st.metric("SMS ارسال شده", sent)
st.metric("SMS بلاک شده", blocked)
st.metric("تعداد AI Call", ai_calls)
st.metric("هزینه تخمینی AI (دلار)", f"{cost_ai:.4f}")
st.metric("هزینه SMS صرفه‌جویی‌شده (دلار)", f"{cost_sms_saved:.2f}")
