"""AgentAction table for the Actions Agent (ai/actions/).

A drafted, confirm-pending banking action (a phone/name transfer today) plus
its lifecycle-status enum. Feature-local: adds one table and one enum, and
touches nothing else. Branches straight off the current single head.

Revision ID: 0047_agent_actions
Revises: 0046_merge_heads
Create Date: 2026-08-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_agent_actions"
down_revision: Union[str, None] = "0046_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_VALUES = (
    "DRAFT",
    "CONFIRMED",
    "EXECUTED",
    "EXPIRED",
    "CANCELLED",
    "FAILED",
    "SUPERSEDED",
    "NEEDS_REVIEW",
)


def upgrade() -> None:
    bind = op.get_bind()
    status_enum = postgresql.ENUM(*_STATUS_VALUES, name="ai_agent_action_status")
    status_enum.create(bind, checkfirst=True)

    op.create_table(
        "ai_agent_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(*_STATUS_VALUES, name="ai_agent_action_status", create_type=False),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ai_agent_actions_idempotency_key"),
    )
    op.create_index("ix_ai_agent_actions_user_created", "ai_agent_actions", ["user_id", "created_at"])
    op.create_index("ix_ai_agent_actions_conversation", "ai_agent_actions", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_agent_actions_conversation", table_name="ai_agent_actions")
    op.drop_index("ix_ai_agent_actions_user_created", table_name="ai_agent_actions")
    op.drop_table("ai_agent_actions")
    postgresql.ENUM(name="ai_agent_action_status").drop(op.get_bind(), checkfirst=True)
