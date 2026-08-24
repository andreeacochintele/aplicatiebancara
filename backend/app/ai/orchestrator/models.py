"""Short-term conversation memory for the Orchestrator (last-N-messages
context, not long-term/semantic memory — see service.py's HISTORY_LIMIT).

A flat, append-only per-user message log, not a "conversations" grouping
table: there's no multi-thread/session concept anywhere else in the app
(the Assistant page is one continuous chat per user), so ordering by
`created_at` per `user_id` is the whole query this needs. `role` and
`agent_used` are plain strings, not Postgres enums, on purpose — same
reasoning as notifications/models.py's `type` field: an enum here would
mean every future agent addition touches this migration.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class ConversationMessage(Base):
    __tablename__ = "ai_conversation_messages"
    __table_args__ = (Index("ix_ai_conversation_messages_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_used: Mapped[str | None] = mapped_column(String(50), nullable=True)  # IntentCategory value, or None
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
