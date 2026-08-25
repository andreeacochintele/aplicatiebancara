"""Add ai_conversations and thread ai_conversation_messages onto it
(ChatGPT-style multi-conversation history). Every existing message is
backfilled into one synthetic "Legacy conversation" per user, so no
history is lost — see the task report for row-count verification.

Revision ID: 0031_ai_conversations
Revises: 0030_fraud_unusual_time
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_ai_conversations"
down_revision: Union[str, None] = "0030_fraud_unusual_time"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ai_conversations_user_updated", "ai_conversations", ["user_id", "updated_at"])

    op.add_column(
        "ai_conversation_messages", sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True)
    )

    bind = op.get_bind()

    before = bind.execute(sa.text("SELECT COUNT(*) FROM ai_conversation_messages")).scalar()
    print(f"[0031_ai_conversations] ai_conversation_messages rows before backfill: {before}")

    # One "Legacy conversation" per user with existing messages, spanning
    # that user's actual message timestamps (not "now") — every row that
    # already existed gets assigned to it below.
    bind.execute(
        sa.text(
            """
            INSERT INTO ai_conversations (id, user_id, title, created_at, updated_at)
            SELECT gen_random_uuid(), user_id, 'Legacy conversation', MIN(created_at), MAX(created_at)
            FROM ai_conversation_messages
            GROUP BY user_id
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE ai_conversation_messages AS m
            SET conversation_id = c.id
            FROM ai_conversations AS c
            WHERE c.user_id = m.user_id AND c.title = 'Legacy conversation'
            """
        )
    )

    unassigned = bind.execute(
        sa.text("SELECT COUNT(*) FROM ai_conversation_messages WHERE conversation_id IS NULL")
    ).scalar()
    if unassigned:
        raise RuntimeError(
            f"Backfill left {unassigned} ai_conversation_messages row(s) without a conversation_id — aborting "
            "before making the column NOT NULL."
        )

    after = bind.execute(sa.text("SELECT COUNT(*) FROM ai_conversation_messages")).scalar()
    print(f"[0031_ai_conversations] ai_conversation_messages rows after backfill: {after} (expected {before})")
    if after != before:
        raise RuntimeError(f"Row count changed during backfill: {before} -> {after}. Aborting.")

    op.alter_column("ai_conversation_messages", "conversation_id", nullable=False)
    op.create_foreign_key(
        "fk_ai_conversation_messages_conversation_id",
        "ai_conversation_messages",
        "ai_conversations",
        ["conversation_id"],
        ["id"],
    )
    op.create_index(
        "ix_ai_conversation_messages_conversation_created",
        "ai_conversation_messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_conversation_messages_conversation_created", table_name="ai_conversation_messages")
    op.drop_constraint("fk_ai_conversation_messages_conversation_id", "ai_conversation_messages", type_="foreignkey")
    op.drop_column("ai_conversation_messages", "conversation_id")
    op.drop_index("ix_ai_conversations_user_updated", table_name="ai_conversations")
    op.drop_table("ai_conversations")
