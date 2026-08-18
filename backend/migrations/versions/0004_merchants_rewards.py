"""Merchants, cashback offers and the bank reward points ledger (architecture.md §11).

Completes the rest of the "Migration 4" grouping from architecture.md §43 —
budgets/savings_goals already landed separately in 0003.

Revision ID: 0004_merchants_rewards
Revises: 0003
Create Date: 2026-08-18

Renamed from the plain "0004" during a merge with master: cards_core (also
branching from 0003) had already claimed "0004" there, and the
beneficiaries migration separately claimed it too — three branches off
0003 all wanted "0004". Disambiguated the same way cards_core/credit did
for themselves (descriptive suffix instead of the bare number).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_merchants_rewards"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column(
            "status", sa.Enum("ACTIVE", "INACTIVE", name="merchant_status"), nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "cashback_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("cashback_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("maximum_cashback", sa.Numeric(18, 2), nullable=True),
        sa.Column("minimum_spend", sa.Numeric(18, 2), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status", sa.Enum("ACTIVE", "EXPIRED", name="cashback_offer_status"), nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "reward_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("points_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "reward_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reward_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reward_accounts.id"), nullable=False
        ),
        sa.Column(
            "source_transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True
        ),
        sa.Column("type", sa.Enum("EARN", "SPEND", "ADJUSTMENT", name="reward_transaction_type"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("reward_transactions")
    op.drop_table("reward_accounts")
    sa.Enum(name="reward_transaction_type").drop(op.get_bind(), checkfirst=True)

    op.drop_table("cashback_offers")
    sa.Enum(name="cashback_offer_status").drop(op.get_bind(), checkfirst=True)

    op.drop_table("merchants")
    sa.Enum(name="merchant_status").drop(op.get_bind(), checkfirst=True)
