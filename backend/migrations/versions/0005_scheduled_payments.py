"""Scheduled payments.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id"), nullable=False),
        sa.Column("beneficiary_name", sa.String(255), nullable=False),
        sa.Column("iban", sa.String(34), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column(
            "frequency",
            sa.Enum("ONCE", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY", name="scheduled_payment_frequency"),
            nullable=False,
        ),
        sa.Column("next_run_on", sa.Date(), nullable=False),
        sa.Column("notify_days_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "PAUSED", "CANCELLED", name="scheduled_payment_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_scheduled_payments_owner_user_id", "scheduled_payments", ["owner_user_id"])
    op.create_index("ix_scheduled_payments_source_wallet_id", "scheduled_payments", ["source_wallet_id"])
    op.create_index("ix_scheduled_payments_status_next_run", "scheduled_payments", ["status", "next_run_on"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_payments_status_next_run", table_name="scheduled_payments")
    op.drop_index("ix_scheduled_payments_source_wallet_id", table_name="scheduled_payments")
    op.drop_index("ix_scheduled_payments_owner_user_id", table_name="scheduled_payments")
    op.drop_table("scheduled_payments")
    sa.Enum(name="scheduled_payment_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="scheduled_payment_frequency").drop(op.get_bind(), checkfirst=True)
