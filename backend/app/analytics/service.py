"""Analytics business rules: read-only aggregates over the transaction history."""
import calendar
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.analytics.repository import AnalyticsRepository
from app.analytics.schemas import MonthlyTrendItem, MonthlyTrendResponse, SpendingByType, SpendingByTypeResponse
from app.core.exceptions import ValidationError


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AnalyticsRepository(db)

    def spending_by_type(self, user_id: uuid.UUID, year: int | None, month: int | None) -> SpendingByTypeResponse:
        if (year is None) != (month is None):
            raise ValidationError("year and month must be provided together")

        now = datetime.now(timezone.utc)
        year = year or now.year
        month = month or now.month
        if not 1 <= month <= 12:
            raise ValidationError("month must be between 1 and 12")

        period_start = datetime(year, month, 1, tzinfo=timezone.utc)
        days_in_month = calendar.monthrange(year, month)[1]
        period_end = datetime(year, month, days_in_month, 23, 59, 59, 999999, tzinfo=timezone.utc)

        rows = self.repository.spending_by_type(user_id, period_start, period_end)
        items = [
            SpendingByType(type=tx_type, total_amount=total, currency=currency, transaction_count=count)
            for tx_type, currency, total, count in rows
        ]
        return SpendingByTypeResponse(
            period_start=period_start.date(), period_end=period_end.date(), items=items
        )

    def monthly_trend(self, user_id: uuid.UUID, months: int) -> MonthlyTrendResponse:
        if not 1 <= months <= 24:
            raise ValidationError("months must be between 1 and 24")

        now = datetime.now(timezone.utc)
        start_year, start_month = now.year, now.month - (months - 1)
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        period_start = datetime(start_year, start_month, 1, tzinfo=timezone.utc)

        rows = self.repository.completed_transactions_in_range(user_id, period_start, now)

        # Grouped in Python rather than a SQL date-trunc: keeps the query portable
        # across the Postgres (prod) and SQLite (tests) dialects the app targets.
        buckets: dict[tuple[int, int, str], dict[str, object]] = {}
        for amount, currency, created_at in rows:
            key = (created_at.year, created_at.month, currency)
            bucket = buckets.setdefault(key, {"total": Decimal("0"), "count": 0})
            bucket["total"] += amount
            bucket["count"] += 1

        items = [
            MonthlyTrendItem(year=year, month=month, currency=currency, total_amount=b["total"], transaction_count=b["count"])
            for (year, month, currency), b in sorted(buckets.items())
        ]
        return MonthlyTrendResponse(items=items)
