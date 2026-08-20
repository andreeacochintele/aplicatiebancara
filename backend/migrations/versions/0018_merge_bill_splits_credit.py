"""Merge the payments branch (0015_bill_splits_folders) with the credit branch
(0015_credit_lifecycle -> 0016_card_preferences_cascade -> 0017_credit_currency).

Both independently forked off 0014_merge_cards_rewards and both happened to
number their first migration 0015 — same situation 0009/0010 and 0011/0012
already resolved once before.

Revision ID: 0018_merge_bill_splits_credit
Revises: 0015_bill_splits_folders, 0017_credit_currency
Create Date: 2026-08-20
"""
from typing import Sequence, Union

revision: str = "0018_merge_bill_splits_credit"
down_revision: Union[str, tuple[str, str], None] = ("0015_bill_splits_folders", "0017_credit_currency")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
