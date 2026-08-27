"""Merge the three parallel heads left after today's PRs, all branched off
0035_credit_card_collateral independently: 0036_card_pin_hash (card PIN
storage), 0037_wallet_iban (via 0036_export_jobs_and_categories -> business
export jobs), and 0039_ai_insights_currency (via
0036_budget_merchant_category -> 0037_savings_goal_contributions ->
0038_ai_insights -> AI insights currency). Unrelated DDL on all three
branches, so this is a plain no-op reconciliation — same pattern as every
earlier merge in this history.

Revision ID: 0040_merge_heads
Revises: 0036_card_pin_hash, 0037_wallet_iban, 0039_ai_insights_currency
Create Date: 2026-08-27
"""
from typing import Sequence, Union

revision: str = "0040_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "0036_card_pin_hash",
    "0037_wallet_iban",
    "0039_ai_insights_currency",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
