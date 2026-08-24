"""Add ai_conversation_messages (short-term orchestrator chat history).

Revision ID: 0029_ai_conversation_messages
Revises: 0028_admin_audit_log
Create Date: 2026-08-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_ai_conversation_messages"
down_revision: Union[str, None] = "0028_admin_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("agent_used", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_conversation_messages_user_created",
        "ai_conversation_messages",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_conversation_messages_user_created", table_name="ai_conversation_messages")
    op.drop_table("ai_conversation_messages")
