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
            raise ValueError("شماره فقط باید عدد باشد (با + اختیاری در ابتدای شماره).")
        if not (10 <= len(digits) <= 15):
            raise ValueError("طول شماره (بدون +) باید بین 10 تا 15 رقم باشد.")
        return "+" + digits

    if not phone.isdigit():
        raise ValueError("شماره فقط باید عدد باشد (با + اختیاری در ابتدای شماره).")
    if not (10 <= len(phone) <= 15):
        raise ValueError("طول شماره باید بین 10 تا 15 رقم باشد.")
    return phone


def _segment_count(text: str) -> int:
    return max(1, (len(text) + 159) // 160)


st.title("ارسال اس ام اس")

if not BACKEND_URL:
    st.error("Missing BACKEND_URL env var (example: http://backend:8000).")
    st.stop()


with st.form("sms_test_form", clear_on_submit=False):
    col1, col2 = st.columns([2, 3])
    with col1:
        phone = st.text_input("شماره موبایل", placeholder="09121234567")
    with col2:
        body = st.text_area("متن پیام", height=140, placeholder="...متن پیام")

    submitted = st.form_submit_button("ارسال")

if body:
    st.info(f"طول پیام: {len(body)} کاراکتر — تعداد سگمنت تقریبی: {_segment_count(body)}")

if submitted:
    body_norm = (body or "").strip()

    if not (phone or "").strip():
        st.error("شماره موبایل الزامی است.")
        st.stop()
    if not body_norm:
        st.error("متن پیام الزامی است.")
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

    st.success("در صف قرار گرفت.")
    request_id = payload.get("request_id")
    if request_id is not None:
        st.info(f"request_id: {request_id}")
    st.json(payload)

st.divider()
st.subheader("بررسی وضعیت پیام‌رسان")
st.caption("بعد از ارسال، پیام‌رسان برای پیام `message_id` می‌سازد. آن مقدار را اینجا وارد کنید.")
status_message_id = st.text_input("message_id", placeholder="شناسه پیام از پیام‌رسان")
check_status = st.button("بررسی وضعیت")

if check_status:
    mid = (status_message_id or "").strip()
    if not mid:
        st.error("message_id را وارد کنید.")
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

    st.success("وضعیت دریافت شد.")
    st.json(payload)
