"""ai_insights.period_key — scope spending-recommendation caching per
calendar month, not just per user, so a past month's recommendations can
be cached forever (once generated, its figures never change) while the
real current month keeps refreshing on its existing TTL.

Backfilled from each row's own created_at ("YYYY-MM"), which is exactly
what every pre-existing row implicitly was: generated for whatever the
real current month was at the time.

Revision ID: 0054_ai_insight_period_key
Revises: 0053_merge_heads
Create Date: 2026-09-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_ai_insight_period_key"
down_revision: Union[str, None] = "0053_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_insights", sa.Column("period_key", sa.String(length=7), nullable=True))
    op.execute("UPDATE ai_insights SET period_key = to_char(created_at, 'YYYY-MM') WHERE period_key IS NULL")
    op.alter_column("ai_insights", "period_key", nullable=False)
    op.drop_index("ix_ai_insights_user_created", table_name="ai_insights")
    op.create_index(
        "ix_ai_insights_user_period_created", "ai_insights", ["user_id", "period_key", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_insights_user_period_created", table_name="ai_insights")
    op.create_index("ix_ai_insights_user_created", "ai_insights", ["user_id", "created_at"])
    op.drop_column("ai_insights", "period_key")
