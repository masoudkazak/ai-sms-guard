import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


def normalize_phone(phone_input: str) -> str:
    phone = (phone_input or "").strip()
    if not phone:
        raise ValueError("phone is required")

    phone = re.sub(r"[ \-\(\)]", "", phone)
    if phone.startswith("00"):
        phone = "+" + phone[2:]

    if phone.startswith("+"):
        digits = phone[1:]
        if not digits.isdigit():
            raise ValueError("phone must contain only digits (and an optional leading '+')")
        if not (10 <= len(digits) <= 15):
            raise ValueError("phone length must be 10..15 digits for E.164")
        return "+" + digits

    if not phone.isdigit():
        raise ValueError("phone must contain only digits (and an optional leading '+')")
    if not (10 <= len(phone) <= 15):
        raise ValueError("phone length must be 10..15 digits")
    return phone


class SmsRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=32)
    body: str = Field(..., min_length=1)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return normalize_phone(v)


class DeliveryPredictionResponse(BaseModel):
    probability: float = Field(..., ge=0.0, le=1.0)
    source: str
    note: str
    hour: int = Field(..., ge=0, le=23)
    best_window: str | None = None
