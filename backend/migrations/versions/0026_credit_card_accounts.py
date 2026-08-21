"""Add stored credit card accounts.

Revision ID: 0026_credit_card_accounts
Revises: 0025_merge_heads
Create Date: 2026-08-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_credit_card_accounts"
down_revision: Union[str, None] = "0025_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_card_accounts",
        sa.Column("card_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="RON"),
        sa.Column("credit_limit", sa.Numeric(18, 2), nullable=False),
        sa.Column("used_amount", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("annual_interest_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("credit_card_accounts")
