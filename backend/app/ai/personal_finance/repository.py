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

    def latest_for_user(self, user_id: uuid.UUID, period_key: str) -> AIInsight | None:
        """Used to decide whether the TTL has expired (and, via
        `.insight_type`, which TTL — see insights.get_or_generate) — not
        filtered by `dismissed`, since a dismissed insight still counts as
        "we already checked this period recently" (see insight_service.py).
        Scoped to one period_key ("YYYY-MM") so switching the app-wide month
        selector checks that month's own cache, not some other month's."""
        if is_supabase_session(self.db):
            rows = self.db.fetch_many(
                AIInsight,
                {"user_id": f"eq.{user_id}", "period_key": f"eq.{period_key}", "order": "created_at.desc", "limit": "1"},
            )
            return rows[0] if rows else None
        stmt = (
            select(AIInsight)
            .where(AIInsight.user_id == user_id, AIInsight.period_key == period_key)
            .order_by(AIInsight.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def supersede_active_for_user(self, user_id: uuid.UUID, period_key: str) -> None:
        """Marks every currently-active insight for this one period_key
        dismissed, without deleting rows — called right before writing a
        fresh batch for that period (see insights.generate_and_store) so a
        regeneration replaces that period's previous batch instead of
        piling new rows on top of stale ones. Scoped to period_key so
        regenerating (or dismissing) one month's insights never touches
        another month's already-cached batch. Caller is responsible for the
        flush (it's about to add more rows of its own in the same unit of
        work)."""
        for insight in self.list_active_for_user(user_id, period_key, limit=100):
            insight.dismissed = True

    def list_active_for_user(self, user_id: uuid.UUID, period_key: str, limit: int = 10) -> list[AIInsight]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                AIInsight,
                {
                    "user_id": f"eq.{user_id}",
                    "period_key": f"eq.{period_key}",
                    "dismissed": "eq.false",
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )
        stmt = (
            select(AIInsight)
            .where(AIInsight.user_id == user_id, AIInsight.period_key == period_key, AIInsight.dismissed.is_(False))
            .order_by(AIInsight.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
