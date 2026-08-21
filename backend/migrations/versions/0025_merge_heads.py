"""Merge the two parallel resolutions of the 0016/0023 head split: this
branch's 0024_merge_notif_card (renamed from 0024_merge_notifications_card_tier
— see that file) and master's own 0024_merge_heads (which resolved it
independently via its own 0023_merge_heads).

Revision ID: 0025_merge_heads
Revises: 0024_merge_heads, 0024_merge_notif_card
Create Date: 2026-08-21
"""
from typing import Sequence, Union

revision: str = "0025_merge_heads"
down_revision: Union[str, tuple[str, str], None] = ("0024_merge_heads", "0024_merge_notif_card")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
