"""Real wallet-backed savings goal contributions and withdrawals.

Adds SAVINGS_CONTRIBUTION / SAVINGS_WITHDRAWAL to transaction_type (a real
Transaction + WalletLedgerEntry now backs a contribution, instead of
SavingsGoal.current_amount just being incremented in place) and a status
column to savings_goals (ACTIVE / COMPLETED / WITHDRAWN).

Revision ID: 0037_savings_goal_contributions
Revises: 0036_budget_merchant_category
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_savings_goal_contributions"
down_revision: Union[str, None] = "0036_budget_merchant_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'SAVINGS_CONTRIBUTION'")
        op.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'SAVINGS_WITHDRAWAL'")

    sa.Enum("ACTIVE", "COMPLETED", "WITHDRAWN", name="savings_goal_status").create(bind, checkfirst=True)
    status = sa.Enum("ACTIVE", "COMPLETED", "WITHDRAWN", name="savings_goal_status", create_type=False)
    op.add_column(
        "savings_goals",
        sa.Column("status", status, nullable=False, server_default="ACTIVE"),
    )
    op.execute("ALTER TABLE savings_goals ALTER COLUMN status DROP DEFAULT")


def downgrade() -> None:
    op.drop_column("savings_goals", "status")
    sa.Enum(name="savings_goal_status").drop(op.get_bind(), checkfirst=True)
    # transaction_type's new values are intentionally not removed on
    # downgrade — Postgres cannot drop individual enum values.
