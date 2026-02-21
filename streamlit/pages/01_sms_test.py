import os
import re

import requests
import streamlit as st


BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")


def _normalize_phone(raw: str) -> str:
    phone = (raw or "").strip()
    phone = re.sub(r"[ \\-\\(\\)]", "", phone)
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


def _segment_count(text: str) -> int:
    return max(1, (len(text) + 159) // 160)


st.title("Send SMS")

if not BACKEND_URL:
    st.error("Missing BACKEND_URL env var (example: http://backend:8000).")
    st.stop()


with st.form("sms_test_form", clear_on_submit=False):
    col1, col2 = st.columns([2, 3])
    with col1:
        phone = st.text_input("Mobile Number", placeholder="09121234567")
    with col2:
        body = st.text_area("Message Body", height=140, placeholder="Type your message...")

    submitted = st.form_submit_button("Send")

if body:
    st.info(f"Message length: {len(body)} chars | Estimated segments: {_segment_count(body)}")

if submitted:
    body_norm = (body or "").strip()

    if not (phone or "").strip():
        st.error("Mobile number is required.")
        st.stop()
    if not body_norm:
        st.error("Message body is required.")
        st.stop()

    try:
        phone_norm = _normalize_phone(phone)
    except ValueError as e:
        st.error(str(e))
        st.stop()

    try:
        resp = requests.post(
            f"{BACKEND_URL}/sms",
            json={"phone": phone_norm, "body": body_norm},
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

    st.success("Queued successfully.")
    request_id = payload.get("request_id")
    if request_id is not None:
        st.info(f"request_id: {request_id}")
    st.json(payload)

st.divider()
st.subheader("Check Provider Status")
st.caption("After sending, the provider creates a `message_id`. Enter it here.")
status_message_id = st.text_input("message_id", placeholder="Provider message ID")
check_status = st.button("Check Status")

if check_status:
    mid = (status_message_id or "").strip()
    if not mid:
        st.error("Please enter message_id.")
        st.stop()

    try:
        resp = requests.get(
            f"{BACKEND_URL}/sms/status",
            params={"message_id": mid},
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

    st.success("Status fetched successfully.")
    st.json(payload)
