"""fraud_cases and fraud_flags — deterministic fraud engine output (architecture.md §32).

Revision ID: 0026_fraud_cases
Revises: 0025_merge_heads
Create Date: 2026-08-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_fraud_cases"
down_revision: Union[str, None] = "0025_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fraud_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING_REVIEW", "APPROVED", "REJECTED", name="fraud_case_status"),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
        sa.Column("hold_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_analysis", sa.Text(), nullable=True),
    )

    op.create_table(
        "fraud_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fraud_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fraud_cases.id"), nullable=False),
        sa.Column(
            "code",
            sa.Enum(
                "NEW_DEVICE",
                "HIGH_AMOUNT",
                "UNUSUAL_COUNTRY",
                "REWARD_ABUSE_PATTERN",
                "HIGH_VELOCITY",
                name="fraud_flag_code",
            ),
            nullable=False,
        ),
        sa.Column("points", sa.Numeric(5, 2), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fraud_flags")
    sa.Enum(name="fraud_flag_code").drop(op.get_bind(), checkfirst=True)

    op.drop_table("fraud_cases")
    sa.Enum(name="fraud_case_status").drop(op.get_bind(), checkfirst=True)
