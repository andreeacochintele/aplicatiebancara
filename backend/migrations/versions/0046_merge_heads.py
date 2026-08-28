"""Merge the three heads left after merging master into
feature/onboarding-identity-document: 0040_identity_documents (this
branch's new identity_documents table, branched off
0039_ai_insights_currency before master's own 0040_merge_heads
reconciliation existed), 0043_repair_card_pin_hash (a pre-existing second
head off 0042_wallet_balance_nonnegative, parallel to
0043_export_format_mt940 - not introduced by this branch), and
0045_wallet_nickname_multi_currency (tip of master's main line). Unrelated
DDL on all three branches, so this is a plain no-op reconciliation - same
pattern as every earlier merge in this history.

Revision ID: 0046_merge_heads
Revises: 0040_identity_documents, 0043_repair_card_pin_hash, 0045_wallet_nickname_multi_currency
Create Date: 2026-08-28
"""
from typing import Sequence, Union

revision: str = "0046_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "0040_identity_documents",
    "0043_repair_card_pin_hash",
    "0045_wallet_nickname_multi_currency",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
