"""Backfill missing credit currency and loan dates.

Revision ID: 0030_credit_currency_dates
Revises: 0029_ai_conversation_messages
Create Date: 2026-08-24

Note: the revision id was shortened from
0030_backfill_credit_currency_and_dates (39 chars) to fit Alembic's
default alembic_version.version_num column (varchar(32)) -- the same
truncation failure this project's history has already hit more than once.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_credit_currency_dates"
down_revision: Union[str, None] = "0029_ai_conversation_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE credit_applications SET currency = 'RON' WHERE currency IS NULL")
    op.execute("UPDATE loans SET currency = 'RON' WHERE currency IS NULL")
    op.execute(
        """
        UPDATE loans
        SET start_date = COALESCE(start_date, DATE(created_at), CURRENT_DATE),
            maturity_date = COALESCE(maturity_date, DATE(created_at), CURRENT_DATE),
            next_payment_date = COALESCE(next_payment_date, DATE(created_at), CURRENT_DATE)
        WHERE start_date IS NULL
           OR maturity_date IS NULL
           OR next_payment_date IS NULL
        """
    )

    op.alter_column("credit_applications", "currency", existing_type=sa.String(length=3), nullable=False)
    op.alter_column("loans", "currency", existing_type=sa.String(length=3), nullable=False)
    op.alter_column("loans", "start_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("loans", "maturity_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("loans", "next_payment_date", existing_type=sa.Date(), nullable=False)


def downgrade() -> None:
    op.alter_column("loans", "next_payment_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("loans", "maturity_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("loans", "start_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("loans", "currency", existing_type=sa.String(length=3), nullable=True)
    op.alter_column("credit_applications", "currency", existing_type=sa.String(length=3), nullable=True)
