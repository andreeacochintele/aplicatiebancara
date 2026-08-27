"""Data-access layer for AIInsight."""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.personal_finance.models import AIInsight
from app.supabase import is_supabase_session


class AIInsightRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, insight: AIInsight) -> AIInsight:
        if is_supabase_session(self.db):
            return self.db.add(insight)
        self.db.add(insight)
        self.db.flush()
        return insight

    def get_by_id(self, insight_id: uuid.UUID) -> AIInsight | None:
        return self.db.get(AIInsight, insight_id)

    def latest_created_at(self, user_id: uuid.UUID) -> datetime | None:
        """Used to decide whether the 24h TTL has expired — not filtered by
        `dismissed`, since a dismissed insight still counts as "we already
        checked this user recently" (see insight_service.py)."""
        if is_supabase_session(self.db):
            rows = self.db.fetch_many(
                AIInsight, {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "1"}
            )
            return rows[0].created_at if rows else None
        stmt = (
            select(AIInsight.created_at)
            .where(AIInsight.user_id == user_id)
            .order_by(AIInsight.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def supersede_active_for_user(self, user_id: uuid.UUID) -> None:
        """Marks every currently-active insight dismissed, without deleting
        rows — called right before writing a fresh batch (see
        insights.generate_and_store) so a regeneration replaces the
        previous batch instead of piling new rows on top of stale ones.
        Caller is responsible for the flush (it's about to add more rows
        of its own in the same unit of work)."""
        for insight in self.list_active_for_user(user_id, limit=100):
            insight.dismissed = True

    def list_active_for_user(self, user_id: uuid.UUID, limit: int = 10) -> list[AIInsight]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                AIInsight,
                {
                    "user_id": f"eq.{user_id}",
                    "dismissed": "eq.false",
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )
        stmt = (
            select(AIInsight)
            .where(AIInsight.user_id == user_id, AIInsight.dismissed.is_(False))
            .order_by(AIInsight.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
