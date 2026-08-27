"""AIInsight — cached, LLM-phrased spending recommendations for the
Analytics dashboard's "Spending recommendations" panel (see
insights.py). Generated lazily with a 24h TTL per user
(insight_service.py) rather than live on every page load, and not via a
background scheduler — this project has no job runner yet (checked: no
APScheduler/Celery/cron anywhere in the repo).

insight_type is a plain string, not a Postgres enum, same reasoning as
ai/orchestrator/models.py's `role`/`agent_used`: it holds
AnalyticsService.spending_recommendations()'s `reasons` values (or
"ALL_CLEAR" when nothing was flagged) — a future new reason type
shouldn't require a migration to add.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class AIInsight(Base):
    __tablename__ = "ai_insights"
    __table_args__ = (Index("ix_ai_insights_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # The merchant category this insight is about (Retail/Food/Travel/...),
    # or None for a category-less "all clear" row (see insights.py).
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Every comparison in AnalyticsService.spending_recommendations() is
    # scoped to one currency at a time (a category can appear once per
    # currency it was actually spent in — see that method's docstring), so
    # an insight about "Travel" is really about Travel in ONE currency.
    # Stored explicitly (not left to the LLM's phrasing) so the UI can
    # show it — omitting it made a EUR-scoped share-of-total look like it
    # contradicted the RON-scoped donut chart on the same page.
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    insight_type: Mapped[str] = mapped_column(String(100), nullable=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
