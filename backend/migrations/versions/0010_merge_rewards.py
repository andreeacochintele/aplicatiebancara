"""Merge the rewards/merchants branch (0003 -> ... -> 0005_reward_tiers_benefits)
with the cards/credit/payments branch (already merged at 0009_merge_payments_cards).

Both branches independently forked off 0003_budgets_savings; this just joins
the two heads back into one, same as 0009 already did for its two parents.

Revision ID: 0010_merge_rewards
Revises: 0009_merge_payments_cards, 0005_reward_tiers_benefits
Create Date: 2026-08-18
"""
from typing import Sequence, Union

revision: str = "0010_merge_rewards"
down_revision: Union[str, tuple[str, str], None] = ("0009_merge_payments_cards", "0005_reward_tiers_benefits")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
