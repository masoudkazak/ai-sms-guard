from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class SmsStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    IN_REVIEW = "IN_REVIEW"
    IN_DLQ = "IN_DLQ"


class Base(DeclarativeBase):
    pass


class SmsEvent(Base):
    __tablename__ = "sms_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=SmsStatus.PENDING.value)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    segment_count: Mapped[int] = mapped_column(Integer, default=1)
    last_dlr: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    ai_calls: Mapped[list["AiCall"]] = relationship("AiCall", back_populates="sms_event")


class AiCall(Base):
    __tablename__ = "ai_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sms_event_id: Mapped[int] = mapped_column(ForeignKey("sms_events.id"), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    decision: Mapped[str] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    sms_event: Mapped["SmsEvent | None"] = relationship("SmsEvent", back_populates="ai_calls")
