"""Merge the notifications branch (0023_notifications) with
0016_benefit_card_tier_gating — a head master has carried unresolved
since it first forked off 0015_transaction_card_id.

Revision ID: 0024_merge_notif_card_tier
Revises: 0016_benefit_card_tier_gating, 0023_notifications
Create Date: 2026-08-21

Note: the revision id was shortened from 0024_merge_notifications_card_tier
(34 chars) to fit Alembic's default alembic_version.version_num column
(varchar(32)), which was crashing `alembic upgrade head` for everyone.
"""
from typing import Sequence, Union

revision: str = "0024_merge_notif_card_tier"
down_revision: Union[str, tuple[str, str], None] = ("0016_benefit_card_tier_gating", "0023_notifications")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
