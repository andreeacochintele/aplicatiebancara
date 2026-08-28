"""Merge heads: 0043_repair_card_pin_hash (cards.pin_hash repair) forked
independently from 0043_export_format_mt940's chain — both branched off
0042_wallet_balance_nonnegative. Unrelated DDL on both branches, so this is
a plain no-op reconciliation — same pattern as every earlier merge in this
history.

Revision ID: 0046_merge_heads
Revises: 0043_repair_card_pin_hash, 0045_wallet_nickname_multi_currency
Create Date: 2026-08-28
"""
from typing import Sequence, Union

revision: str = "0046_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "0043_repair_card_pin_hash",
    "0045_wallet_nickname_multi_currency",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
