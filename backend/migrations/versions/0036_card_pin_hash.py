"""Add hashed card PINs.

Revision ID: 0036_card_pin_hash
Revises: 0035_credit_card_collateral
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_card_pin_hash"
down_revision: Union[str, None] = "0035_credit_card_collateral"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("pin_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("cards", "pin_hash")
