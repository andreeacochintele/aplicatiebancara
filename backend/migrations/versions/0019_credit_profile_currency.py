"""Add currency to credit profiles.

Revision ID: 0019_credit_profile_currency
Revises: 0018_merge_payments_credit
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_credit_profile_currency"
down_revision: Union[str, None] = "0018_merge_payments_credit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("credit_profiles", sa.Column("currency", sa.String(3), nullable=True))
    op.execute("UPDATE credit_profiles SET currency = 'RON' WHERE currency IS NULL")
    op.alter_column("credit_profiles", "currency", nullable=False)


def downgrade() -> None:
    op.drop_column("credit_profiles", "currency")
