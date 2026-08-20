"""Merge three branches that all forked off 0014_merge_cards_rewards and
independently reused 0015/0016/0017 as revision numbers: bill splits +
transaction folders (Payments), credit lifecycle + card cascade + credit
currency (Cards/Credit), and benefit card-tier gating (Intelligence/Rewards).
Same resolution pattern as the earlier 0009/0010 and 0014 merges in this
history.

Revision ID: 0018_merge_heads
Revises: 0015_bill_splits_folders, 0016_benefit_card_tier_gating, 0017_credit_currency
Create Date: 2026-08-20
"""
from typing import Sequence, Union

revision: str = "0018_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "0015_bill_splits_folders",
    "0016_benefit_card_tier_gating",
    "0017_credit_currency",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
