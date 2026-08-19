"""Add sandbox-only mock PAN for card reveal.

Revision ID: 0013_card_mock_pan
Revises: 0012_card_mock_cvv
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_card_mock_pan"
down_revision: Union[str, None] = "0012_card_mock_cvv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("mock_pan", sa.String(length=19), nullable=True))
    op.execute(
        """
        UPDATE cards
        SET mock_pan =
            '4000 '
            || lpad((floor(random() * 10000))::int::text, 4, '0')
            || ' '
            || lpad((floor(random() * 10000))::int::text, 4, '0')
            || ' '
            || last_four
        WHERE mock_pan IS NULL
        """
    )
    op.alter_column("cards", "mock_pan", nullable=False)


def downgrade() -> None:
    op.drop_column("cards", "mock_pan")
