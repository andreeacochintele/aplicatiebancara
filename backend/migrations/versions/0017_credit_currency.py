"""Add currency to credit applications and loans.

Revision ID: 0017_credit_currency
Revises: 0016_card_preferences_cascade
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_credit_currency"
down_revision: Union[str, None] = "0016_card_preferences_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("credit_applications", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("loans", sa.Column("currency", sa.String(3), nullable=True))
    op.execute("UPDATE credit_applications SET currency = 'RON' WHERE currency IS NULL")
    op.execute("UPDATE loans SET currency = 'RON' WHERE currency IS NULL")
    op.alter_column("credit_applications", "currency", nullable=False)
    op.alter_column("loans", "currency", nullable=False)


def downgrade() -> None:
    op.drop_column("loans", "currency")
    op.drop_column("credit_applications", "currency")
