import os
import re
import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
if not BACKEND_URL:
    st.error("Missing BACKEND_URL env var (example: http://backend:8000).")
    st.stop()


def _normalize_phone(raw: str) -> str:
    phone = (raw or "").strip()
    phone = re.sub(r"[ \-\(\)]", "", phone)
    if phone.startswith("00"):
        phone = "+" + phone[2:]

    if phone.startswith("+"):
        digits = phone[1:]
        if not digits.isdigit():
            raise ValueError("Phone must contain only digits (with an optional leading +).")
        if not (10 <= len(digits) <= 15):
            raise ValueError("Phone length (without +) must be between 10 and 15 digits.")
        return "+" + digits

    if not phone.isdigit():
        raise ValueError("Phone must contain only digits (with an optional leading +).")
    if not (10 <= len(phone) <= 15):
        raise ValueError("Phone length must be between 10 and 15 digits.")
    return phone


st.title("Predict SMS Delivery Probability")

with st.form("predict_form"):
    col1, col2 = st.columns([2, 1])
    with col1:
        phone = st.text_input("Mobile Number", placeholder="09121234567")
    with col2:
        hour = st.number_input("Hour (UTC)", min_value=0, max_value=24, value=12, step=1)
    submitted = st.form_submit_button("Predict")

if submitted:
    if not phone.strip():
        st.error("Mobile number is required.")
        st.stop()

    try:
        phone_norm = _normalize_phone(phone)
    except ValueError as e:
        st.error(str(e))
        st.stop()

    try:
        resp = requests.get(
            f"{BACKEND_URL}/sms/predict-delivery",
            params={"phone": phone_norm, "hour": int(hour)},
            timeout=15,
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            st.error(f"Backend error: HTTP {resp.status_code}")
            st.json(payload)
            st.stop()
    except Exception as e:
        st.error(f"Backend error: {e}")
        st.stop()

    st.success("Prediction fetched successfully.")
    st.subheader("Prediction Result")
    st.json(payload)

    probability = payload.get("probability")
    note = payload.get("note")
    best_window = payload.get("best_window")
    stat_rate = payload.get("stat_rate")
    llm_rate = payload.get("llm_rate")
    llm_weight = payload.get("llm_weight")

    st.metric("Probability", f"{probability}")
    st.metric("Best Window", best_window)
    st.metric("Note", note)
    if stat_rate is not None:
        st.metric("Statistical Rate", stat_rate)
    if llm_rate is not None:
        st.metric("LLM Rate", llm_rate)
    if llm_weight is not None:
        st.metric("LLM Weight", llm_weight)