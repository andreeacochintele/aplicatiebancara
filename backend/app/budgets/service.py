"""Budget business rules.

Spend-vs-limit tracking only works for budgets that carry a `category` —
matched against the paying merchant's own Merchant.category (see
BudgetRepository.spent_amount). A budget without one simply reports zero
spent rather than guessing a match from free-text transaction descriptions.
"""
import calendar
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.budgets.models import Budget, BudgetPeriod
from app.budgets.repository import BudgetRepository
from app.budgets.schemas import BudgetCreate, BudgetPublic
from app.core.exceptions import NotFoundError, ValidationError


class BudgetService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = BudgetRepository(db)

    def create_budget(self, user_id: uuid.UUID, data: BudgetCreate) -> BudgetPublic:
        if data.limit_amount <= 0:
            raise ValidationError("limit_amount must be positive")

        budget = Budget(
            user_id=user_id,
            category=data.category,
            name=data.name,
            limit_amount=data.limit_amount,
            currency=data.currency.upper(),
            period=data.period,
        )
        self.repository.add(budget)
        return self._to_public(budget)

    def list_budgets(
        self, user_id: uuid.UUID, year: int | None = None, month: int | None = None
    ) -> list[BudgetPublic]:
        """`year`/`month` re-point monthly budgets at a month other than the
        current one, so the app-wide period selector can show what a budget
        looked like in, say, August while it is already September. Same
        validation shape as AnalyticsService._month_period_bounds()."""
        if (year is None) != (month is None):
            raise ValidationError("year and month must be provided together")
        if month is not None and not 1 <= month <= 12:
            raise ValidationError("month must be between 1 and 12")
        return [self._to_public(budget, year, month) for budget in self.repository.list_for_user(user_id)]

    def delete_budget(self, user_id: uuid.UUID, budget_id: uuid.UUID) -> None:
        budget = self.repository.get_by_id(budget_id)
        if budget is None or budget.user_id != user_id:
            raise NotFoundError("Budget not found")
        self.repository.delete(budget)

    def _to_public(self, budget: Budget, year: int | None = None, month: int | None = None) -> BudgetPublic:
        now = datetime.now(timezone.utc)
        period_start, period_end = self._period_bounds(budget.period, now, year, month)

        spent = (
            self.repository.spent_amount(budget.user_id, budget.category, budget.currency, period_start, period_end)
            if budget.category is not None
            else Decimal("0")
        )
        percent_used = round(float(spent / budget.limit_amount) * 100, 1) if budget.limit_amount else 0.0
        days_remaining = max((period_end.date() - now.date()).days, 0)

        return BudgetPublic(
            id=budget.id,
            name=budget.name,
            category=budget.category,
            limit_amount=budget.limit_amount,
            currency=budget.currency,
            period=budget.period,
            spent_amount=spent,
            percent_used=percent_used,
            remaining_amount=budget.limit_amount - spent,
            period_end=period_end.date(),
            days_remaining=days_remaining,
            created_at=budget.created_at,
        )

    def _period_bounds(
        self,
        period: BudgetPeriod,
        now: datetime,
        year: int | None = None,
        month: int | None = None,
    ) -> tuple[datetime, datetime]:
        if period == BudgetPeriod.MONTHLY:
            # An explicit year/month stands in for "which month is now".
            target_year = year if year is not None else now.year
            target_month = month if month is not None else now.month
            start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
            days_in_month = calendar.monthrange(target_year, target_month)[1]
            end = datetime(target_year, target_month, days_in_month, 23, 59, 59, tzinfo=timezone.utc)
        else:
            # Weekly budgets deliberately ignore the override: "which week of
            # August" has no answer, so they stay on the real current week
            # rather than being given an arbitrary one.
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        return start, end
