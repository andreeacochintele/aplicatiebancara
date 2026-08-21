"""Merge the notifications branch (0023_notifications) with
0016_benefit_card_tier_gating — a head master has carried unresolved
since it first forked off 0015_transaction_card_id.

Revision ID: 0024_merge_notif_card
Revises: 0016_benefit_card_tier_gating, 0023_notifications
Create Date: 2026-08-21

Note: originally created as "0024_merge_notifications_card_tier" (35
chars), which overflows alembic_version.version_num's VARCHAR(32) and
rolls back the entire multi-branch upgrade transaction — the same
truncation failure this project's history has already hit more than
once. Renamed only the id; the merge itself is unchanged.
"""
from typing import Sequence, Union

revision: str = "0024_merge_notif_card"
down_revision: Union[str, tuple[str, str], None] = ("0016_benefit_card_tier_gating", "0023_notifications")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
