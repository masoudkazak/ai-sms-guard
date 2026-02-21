"""Make message_id nullable and add provider_status

Revision ID: 003
Revises: 002
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("sms_events", "message_id", existing_type=sa.String(length=64), nullable=True)
    op.add_column("sms_events", sa.Column("provider_status", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("sms_events", "provider_status")
    op.alter_column("sms_events", "message_id", existing_type=sa.String(length=64), nullable=False)
