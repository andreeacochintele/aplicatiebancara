"""Merge two heads left after syncing feature/user-onboarding-profile with
master: this branch's own 0022_user_onboarding_profile vs. master's
0022_merge_heads (rewards/merchants sync). Unrelated DDL on both sides, so
this is a plain no-op reconciliation.

Revision ID: 0023_merge_heads
Revises: 0022_merge_heads, 0022_user_onboarding_profile
Create Date: 2026-08-21
"""
from typing import Sequence, Union


revision: str = "0023_merge_heads"
down_revision: Union[str, Sequence[str], None] = ("0022_merge_heads", "0022_user_onboarding_profile")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
