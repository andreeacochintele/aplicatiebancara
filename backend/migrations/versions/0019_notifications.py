"""Notifications table (architecture.md §26).

Revision ID: 0019_notifications
Revises: 0018_merge_bill_splits_credit
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_notifications"
down_revision: Union[str, None] = "0018_merge_bill_splits_credit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTIFICATION_TYPE = postgresql.ENUM(
    "TRANSACTION",
    "FRAUD",
    "PAYMENT_REMINDER",
    "CASHBACK",
    "CREDIT",
    "SPLIT_BILL",
    "SYSTEM",
    name="notification_type",
    create_type=False,  # created explicitly below; without this, create_table()
    # tries to emit CREATE TYPE a second time and the migration fails with
    # "type notification_type already exists".
)


def upgrade() -> None:
    NOTIFICATION_TYPE.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", NOTIFICATION_TYPE, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column(
            "related_transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    NOTIFICATION_TYPE.drop(op.get_bind(), checkfirst=True)
