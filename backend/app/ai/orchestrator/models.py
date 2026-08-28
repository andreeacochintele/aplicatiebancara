"""Conversation memory for the Orchestrator: a ChatGPT-style multi-thread
model. `Conversation` is a per-user thread (title, timestamps);
`ConversationMessage` rows belong to exactly one conversation
(`conversation_id`, migration 0031). Short-term LLM context
(service.py's HISTORY_LIMIT) is always scoped to a single conversation —
never across a user's other conversations.

Before migration 0031 this was a single flat per-user log with no
conversation grouping; every message that existed at that point was
backfilled into one synthetic "Legacy conversation" per user (see
0031_ai_conversations.py) so no history was lost.

`role` and `agent_used` are plain strings, not Postgres enums, on
purpose — same reasoning as notifications/models.py's `type` field: an
enum here would mean every future agent addition touches this migration.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class Conversation(Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (Index("ix_ai_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Bumped explicitly in service.py whenever a message is appended — not
    # a SQLAlchemy onupdate=, so this also works under the Supabase REST
    # adapter (app/supabase.py), which has no ORM-level update hooks.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationMessage(Base):
    __tablename__ = "ai_conversation_messages"
    __table_args__ = (
        Index("ix_ai_conversation_messages_user_created", "user_id", "created_at"),
        Index("ix_ai_conversation_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_used: Mapped[str | None] = mapped_column(String(50), nullable=True)  # IntentCategory value, or None
    # Set on the assistant message when the actions agent drafted something
    # (ai/actions/). Lets the UI re-hydrate the confirm card with its
    # current status after a conversation is reopened — the card's live
    # state lives in ai_agent_actions, this is just the link back to it.
    action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
