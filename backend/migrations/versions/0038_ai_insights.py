"""Add ai_insights - cached, LLM-phrased spending recommendations for the
Analytics dashboard (see app/ai/personal_finance/models.py, insights.py).

Revision ID: 0038_ai_insights
Revises: 0037_savings_goal_contributions
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038_ai_insights"
down_revision: Union[str, None] = "0037_savings_goal_contributions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("insight_type", sa.String(length=100), nullable=False),
        sa.Column("dismissed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_insights_user_created", "ai_insights", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_insights_user_created", table_name="ai_insights")
    op.drop_table("ai_insights")
