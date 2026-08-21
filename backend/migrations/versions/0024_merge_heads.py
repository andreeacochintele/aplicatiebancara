"""Merge two heads left after syncing feature/user-onboarding-profile with
master a second time: this branch's own 0023_merge_heads vs. master's
0023_notifications (new notifications module), both descending from
0022_merge_heads independently. Unrelated DDL on both sides, so this is a
plain no-op reconciliation.

Revision ID: 0024_merge_heads
Revises: 0023_merge_heads, 0023_notifications
Create Date: 2026-08-21
"""
from typing import Sequence, Union


revision: str = "0024_merge_heads"
down_revision: Union[str, Sequence[str], None] = ("0023_merge_heads", "0023_notifications")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
