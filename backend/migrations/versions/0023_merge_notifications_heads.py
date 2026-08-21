"""Merge the notifications branch (0019_notifications, forked off
0018_merge_bill_splits_credit) with master's two current heads
(0016_benefit_card_tier_gating and 0022_merge_heads).

Revision ID: 0023_merge_notifications_heads
Revises: 0016_benefit_card_tier_gating, 0019_notifications, 0022_merge_heads
Create Date: 2026-08-21
"""
from typing import Sequence, Union

revision: str = "0023_merge_notifications_heads"
down_revision: Union[str, tuple[str, str, str], None] = (
    "0016_benefit_card_tier_gating",
    "0019_notifications",
    "0022_merge_heads",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
