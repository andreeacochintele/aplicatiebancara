"""Add tiers for reusable cards.

Revision ID: 0011_card_tiers
Revises: 0010_merge_rewards
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_card_tiers"
down_revision: Union[str, None] = "0010_merge_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    card_tier = sa.Enum("REGULAR", "GOLD", "PLATINUM", name="card_tier")
    card_tier.create(op.get_bind(), checkfirst=True)
    op.add_column("cards", sa.Column("tier", card_tier, nullable=True))
    op.execute("UPDATE cards SET tier = 'REGULAR' WHERE type IN ('DEBIT', 'CREDIT') AND tier IS NULL")


def downgrade() -> None:
    op.drop_column("cards", "tier")
    sa.Enum(name="card_tier").drop(op.get_bind(), checkfirst=True)
