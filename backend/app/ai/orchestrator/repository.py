"""Data-access layer for Conversation and ConversationMessage."""
import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.orchestrator.models import Conversation, ConversationMessage
from app.supabase import is_supabase_session


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- conversations ----

    def create_conversation(self, conversation: Conversation) -> Conversation:
        self.db.add(conversation)
        if not is_supabase_session(self.db):
            self.db.flush()
        return conversation

    def get_conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def list_conversations_for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[Conversation]:
        """This user's conversations, most recently updated first."""
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                Conversation,
                {"user_id": f"eq.{user_id}", "order": "updated_at.desc", "limit": str(limit)},
            )
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def touch_conversation(self, conversation: Conversation, updated_at: datetime) -> None:
        conversation.updated_at = updated_at
        if not is_supabase_session(self.db):
            self.db.flush()

    def set_title(self, conversation: Conversation, title: str) -> None:
        conversation.title = title
        if not is_supabase_session(self.db):
            self.db.flush()

    def delete_conversation(self, conversation: Conversation) -> None:
        """Deletes the conversation and all its messages. Messages have a
        plain FK to conversations with no ON DELETE CASCADE (migration
        0031), so messages must be removed first."""
        if is_supabase_session(self.db):
            messages = self.db.fetch_many(ConversationMessage, {"conversation_id": f"eq.{conversation.id}", "limit": "1000"})
            for message in messages:
                self.db.delete(message)
            self.db.delete(conversation)
            return
        self.db.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id))
        self.db.delete(conversation)
        self.db.flush()

    # ---- messages ----

    def add(self, message: ConversationMessage) -> ConversationMessage:
        self.db.add(message)
        if not is_supabase_session(self.db):
            self.db.flush()
        return message

    def list_recent_for_conversation(self, conversation_id: uuid.UUID, limit: int) -> list[ConversationMessage]:
        """Most recent `limit` messages *within this one conversation*,
        newest first — the LLM-context-facing read (see service.py's
        HISTORY_LIMIT). Deliberately scoped to a single conversation_id,
        never across a user's other conversations."""
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                ConversationMessage,
                {"conversation_id": f"eq.{conversation_id}", "order": "created_at.desc", "limit": str(limit)},
            )
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def list_messages_for_conversation(
        self, conversation_id: uuid.UUID, limit: int, before: datetime | None = None
    ) -> list[ConversationMessage]:
        """One page of this conversation's messages, newest first. Without
        `before`, returns the most recent page (what a freshly opened
        conversation should show). With `before`, returns the `limit`
        messages immediately preceding that timestamp — for loading older
        messages on scroll-up. Cursor is a timestamp, not a message id: at
        this app's message volume, two messages in the same conversation
        sharing an identical created_at is not a realistic concern, so this
        stays simple rather than a compound (timestamp, id) cursor."""
        if is_supabase_session(self.db):
            params = {"conversation_id": f"eq.{conversation_id}", "order": "created_at.desc", "limit": str(limit)}
            if before is not None:
                params["created_at"] = f"lt.{before.isoformat()}"
            return self.db.fetch_many(ConversationMessage, params)
        stmt = select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id)
        if before is not None:
            stmt = stmt.where(ConversationMessage.created_at < before)
        stmt = stmt.order_by(ConversationMessage.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def get_last_message_for_conversation(self, conversation_id: uuid.UUID) -> ConversationMessage | None:
        """Latest message in this conversation — used to build the preview
        text in the conversation list."""
        messages = self.list_messages_for_conversation(conversation_id, limit=1)
        return messages[0] if messages else None
