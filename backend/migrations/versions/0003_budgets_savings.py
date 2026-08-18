"""Budgets and savings goals (architecture.md §13, §14).

Scoped to only these two tables, not the full "Migration 4" grouping from
architecture.md §43 — merchants/cashback/rewards land in a separate
migration on a different branch to keep the two independent.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("limit_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column(
            "period", sa.Enum("WEEKLY", "MONTHLY", name="budget_period"), nullable=False,
            server_default="MONTHLY",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "savings_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("target_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("savings_goals")
    op.drop_table("budgets")
    sa.Enum(name="budget_period").drop(op.get_bind(), checkfirst=True)
