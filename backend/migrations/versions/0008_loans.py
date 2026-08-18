"""Loans.

Revision ID: 0008_loans
Revises: 0007_credit_applications
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_loans"
down_revision: Union[str, None] = "0007_credit_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "loans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_applications.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("principal_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("interest_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("monthly_payment", sa.Numeric(18, 2), nullable=False),
        sa.Column("outstanding_principal", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "CLOSED", "DEFAULTED", name="loan_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("loans")
    sa.Enum(name="loan_status").drop(op.get_bind(), checkfirst=True)
