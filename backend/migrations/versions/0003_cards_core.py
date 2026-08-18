"""Cards core.

Revision ID: 0004_cards_core
Revises: 0003
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_cards_core"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("default_wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id"), nullable=True),
        sa.Column("type", sa.Enum("DEBIT", "CREDIT", "ONE_TIME", name="card_type"), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "FROZEN", "EXPIRED", "CANCELLED", name="card_status"), nullable=False),
        sa.Column("masked_pan", sa.String(19), nullable=False),
        sa.Column("last_four", sa.String(4), nullable=False),
        sa.Column("expiration_month", sa.Integer(), nullable=False),
        sa.Column("expiration_year", sa.Integer(), nullable=False),
        sa.Column("one_time_remaining", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("cards")
    sa.Enum(name="card_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="card_type").drop(op.get_bind(), checkfirst=True)
