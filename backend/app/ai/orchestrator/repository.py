"""Data-access layer for ConversationMessage (short-term chat history)."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator.models import ConversationMessage
from app.supabase import is_supabase_session


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, message: ConversationMessage) -> ConversationMessage:
        self.db.add(message)
        if not is_supabase_session(self.db):
            self.db.flush()
        return message

    def list_recent_for_user(self, user_id: uuid.UUID, limit: int) -> list[ConversationMessage]:
        """Most recent `limit` messages for this user, newest first —
        callers that need chronological order (e.g. building LLM context)
        reverse this themselves (see service.py)."""
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                ConversationMessage,
                {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": str(limit)},
            )
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
