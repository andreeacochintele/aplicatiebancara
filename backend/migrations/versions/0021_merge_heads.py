"""Merge two heads that both independently resolved the same 0015/0016/0017
duplicate-numbering fork: this branch's own 0018_merge_heads (which folded in
the Intelligence/Rewards branch too) vs. master's 0018_merge_bill_splits_credit
(created without knowledge of that third branch). Both are no-op pass-through
merges already, so this is just reconciling the two into one head.

Revision ID: 0021_merge_heads
Revises: 0018_merge_bill_splits_credit, 0020_redemption_expiry
Create Date: 2026-08-20
"""
from typing import Sequence, Union

revision: str = "0021_merge_heads"
down_revision: Union[str, tuple[str, str], None] = ("0018_merge_bill_splits_credit", "0020_redemption_expiry")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
