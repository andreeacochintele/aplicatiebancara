"""Add ai_insights.currency — every comparison in
AnalyticsService.spending_recommendations() is scoped to one currency at a
time, so an insight about a category is really about that category in one
currency. Was previously only implied in the LLM-phrased message text,
which made a EUR-scoped share-of-total look like it contradicted a
RON-scoped chart on the same dashboard.

Revision ID: 0039_ai_insights_currency
Revises: 0038_ai_insights
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_ai_insights_currency"
down_revision: Union[str, None] = "0038_ai_insights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_insights", sa.Column("currency", sa.String(length=3), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_insights", "currency")
