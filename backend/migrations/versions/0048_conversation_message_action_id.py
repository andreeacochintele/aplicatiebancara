"""Link an assistant ConversationMessage to the AgentAction it drafted.

Nullable ai_conversation_messages.action_id — lets the assistant UI
re-hydrate a confirm card with its live status (from ai_agent_actions)
when a conversation is reopened or another tab is switched back to.
Feature-local, additive.

Revision ID: 0048_conversation_message_action_id
Revises: 0047_agent_actions
Create Date: 2026-08-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048_conversation_message_action_id"
down_revision: Union[str, None] = "0047_agent_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_conversation_messages",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_conversation_messages", "action_id")
