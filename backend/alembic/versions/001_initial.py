"""Initial schema: sms_events and ai_calls

Revision ID: 001
Revises:
Create Date: 2025-02-15

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sms_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("segment_count", sa.Integer(), nullable=True),
        sa.Column("last_dlr", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_events_message_id", "sms_events", ["message_id"], unique=True)

    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sms_event_id", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["sms_event_id"], ["sms_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ai_calls")
    op.drop_index("ix_sms_events_message_id", table_name="sms_events")
    op.drop_table("sms_events")
