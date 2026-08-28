"""Repair missing card PIN hash column.

Revision ID: 0043_repair_card_pin_hash
Revises: 0042_wallet_balance_nonnegative
Create Date: 2026-08-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0043_repair_card_pin_hash"
down_revision: Union[str, None] = "0042_wallet_balance_nonnegative"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE cards ADD COLUMN IF NOT EXISTS pin_hash VARCHAR(255)")


def downgrade() -> None:
    # No-op: this repair migration may run on databases where 0036 already
    # owns the column. Dropping it here would destroy saved card PINs.
    pass
