"""Replace Budget.category_id (pointed at a transaction_categories table
that was never built) with Budget.category, a free-text merchant category
string matching Merchant.category — the same dimension the Analytics
spending-by-category view groups by.

Revision ID: 0036_budget_merchant_category
Revises: 0035_credit_card_collateral
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_budget_merchant_category"
down_revision: Union[str, None] = "0035_credit_card_collateral"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # category_id was never backed by a real table (no FK existed) and
    # nothing ever wrote a meaningful value into it, so there is no data
    # worth preserving across the type change.
    op.drop_column("budgets", "category_id")
    op.add_column("budgets", sa.Column("category", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("budgets", "category")
    op.add_column("budgets", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
