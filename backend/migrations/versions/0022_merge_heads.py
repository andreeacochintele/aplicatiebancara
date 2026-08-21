"""Merge two heads left after syncing with master again: this branch's own
0021_merge_heads vs. master's newest 0018_merge_payments_credit ->
0019_credit_profile_currency -> 0020_credit_loan_product_type chain.
0018_merge_payments_credit independently re-merges the same
(0015_bill_splits_folders, 0017_credit_currency) pair this branch's
0018_merge_bill_splits_credit already merged — same recurring
duplicate-numbering situation as every earlier merge in this history. Both
sides are otherwise unrelated DDL, so this is a plain no-op reconciliation.

Revision ID: 0022_merge_heads
Revises: 0020_credit_loan_product_type, 0021_merge_heads
Create Date: 2026-08-20
"""
from typing import Sequence, Union

revision: str = "0022_merge_heads"
down_revision: Union[str, tuple[str, str], None] = ("0020_credit_loan_product_type", "0021_merge_heads")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
