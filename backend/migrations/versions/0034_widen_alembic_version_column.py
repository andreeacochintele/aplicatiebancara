"""Widen alembic_version.version_num from the default varchar(32) to
varchar(255).

This is the third time a merge-migration revision id has overflowed the
default column (0024_merge_notifications_card_tier, then
0030_backfill_credit_currency_and_dates, both had to be manually
shortened after already crashing `alembic upgrade head` on a clean
database). Naming discipline alone hasn't stuck across a 4-person team
branching in parallel — widening the column removes the failure mode
outright instead of relying on everyone remembering a 32-char limit.

Revision ID: 0034_widen_alembic_version
Revises: 0033_merge_heads
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_widen_alembic_version"
down_revision: Union[str, None] = "0033_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=255),
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=255),
        type_=sa.String(length=32),
    )
