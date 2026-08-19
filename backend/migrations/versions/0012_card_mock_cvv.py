"""Add sandbox-only mock CVV for cards.

Revision ID: 0012_card_mock_cvv
Revises: 0011_card_tiers
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_card_mock_cvv"
down_revision: Union[str, None] = "0011_card_tiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("mock_cvv", sa.String(length=3), nullable=True))
    op.execute("UPDATE cards SET mock_cvv = lpad((floor(random() * 1000))::int::text, 3, '0') WHERE mock_cvv IS NULL")
    op.alter_column("cards", "mock_cvv", nullable=False)


def downgrade() -> None:
    op.drop_column("cards", "mock_cvv")
