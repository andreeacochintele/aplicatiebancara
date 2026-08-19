"""Merge the rewards/merchants branch (0011_reward_tx_unique -> 0012_merchant_verified)
with the cards branch (0011_card_tiers -> ... -> 0013_card_mock_pan).

Both independently forked off 0010_merge_rewards and both happened to number
their migrations 0011/0012 — same situation 0009/0010 already resolved once
for the payments/cards and rewards/merchants branches.

Revision ID: 0014_merge_cards_rewards
Revises: 0012_merchant_verified, 0013_card_mock_pan
Create Date: 2026-08-19
"""
from typing import Sequence, Union

revision: str = "0014_merge_cards_rewards"
down_revision: Union[str, tuple[str, str], None] = ("0012_merchant_verified", "0013_card_mock_pan")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
