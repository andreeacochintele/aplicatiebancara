"""Data-access layer for AgentAction. Dual-path (SQLAlchemy / Supabase REST)
like every other repository in this codebase."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.actions.models import AgentAction, AgentActionStatus
from app.supabase import is_supabase_session

_RECENT_EXECUTED_WINDOW = timedelta(minutes=10)


class AgentActionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, action: AgentAction) -> AgentAction:
        if is_supabase_session(self.db):
            return self.db.add(action)
        self.db.add(action)
        self.db.flush()
        return action

    def get_by_id(self, action_id: uuid.UUID) -> AgentAction | None:
        return self.db.get(AgentAction, action_id)

    def flush(self) -> None:
        if not is_supabase_session(self.db):
            self.db.flush()

    def list_by_ids(self, action_ids: list[uuid.UUID]) -> list[AgentAction]:
        """Used to embed each action's live state into a page of conversation
        messages — keyed off the messages' own action_id, not the
        conversation, so it still works if an action row's conversation_id is
        somehow unset."""
        if not action_ids:
            return []
        if is_supabase_session(self.db):
            ids = ",".join(str(a) for a in action_ids)
            return self.db.fetch_many(AgentAction, {"id": f"in.({ids})", "limit": str(len(action_ids))})
        stmt = select(AgentAction).where(AgentAction.id.in_(action_ids))
        return list(self.db.scalars(stmt))

    def list_open_drafts_for_conversation(self, conversation_id: uuid.UUID) -> list[AgentAction]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                AgentAction,
                {"conversation_id": f"eq.{conversation_id}", "status": f"eq.{AgentActionStatus.DRAFT.value}"},
            )
        stmt = select(AgentAction).where(
            AgentAction.conversation_id == conversation_id,
            AgentAction.status == AgentActionStatus.DRAFT,
        )
        return list(self.db.scalars(stmt))

    def count_recent_executed(self, user_id: uuid.UUID) -> int:
        """Agent transfers this user has already executed within the recent
        window — feeds fraud_screen's velocity check."""
        cutoff = datetime.now(timezone.utc) - _RECENT_EXECUTED_WINDOW
        if is_supabase_session(self.db):
            rows = self.db.fetch_many(
                AgentAction,
                {
                    "user_id": f"eq.{user_id}",
                    "status": f"eq.{AgentActionStatus.EXECUTED.value}",
                    "executed_at": f"gte.{cutoff.isoformat()}",
                    "limit": "50",
                },
            )
            return len(rows)
        stmt = select(AgentAction).where(
            AgentAction.user_id == user_id,
            AgentAction.status == AgentActionStatus.EXECUTED,
            AgentAction.executed_at >= cutoff,
        )
        return len(list(self.db.scalars(stmt)))
