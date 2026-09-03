"""Analytics endpoints, scoped to the authenticated user."""
import calendar
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.locale import get_locale
from app.ai.personal_finance import insights as ai_insights
from app.ai.personal_finance.schemas import AIInsightPublic
from app.analytics.schemas import (
    BalanceHistoryResponse,
    ForecastResponse,
    MonthlyTrendResponse,
    NetWorthHistoryResponse,
    NetWorthResponse,
    SpendingByCategoryResponse,
    SpendingByTypeResponse,
    TopCounterpartiesResponse,
)
from app.analytics.service import AnalyticsService
from app.auth.dependencies import get_current_user
from app.core.exceptions import ValidationError
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/spending-by-type", response_model=SpendingByTypeResponse)
def get_spending_by_type(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpendingByTypeResponse:
    return AnalyticsService(db).spending_by_type(current_user.id, year, month)


@router.get("/spending-by-category", response_model=SpendingByCategoryResponse)
def get_spending_by_category(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpendingByCategoryResponse:
    return AnalyticsService(db).spending_by_category(current_user.id, year, month)


@router.get("/top-counterparties", response_model=TopCounterpartiesResponse)
def get_top_counterparties(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopCounterpartiesResponse:
    return AnalyticsService(db).top_counterparties(current_user.id, year, month, limit)


@router.get("/monthly-trend", response_model=MonthlyTrendResponse)
def get_monthly_trend(
    months: int = Query(default=6),
    base_currency: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonthlyTrendResponse:
    return AnalyticsService(db).monthly_trend(current_user.id, months, base_currency)


@router.get("/net-worth", response_model=NetWorthResponse)
def get_net_worth(
    base_currency: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NetWorthResponse:
    return AnalyticsService(db).net_worth(current_user.id, base_currency)


@router.get("/net-worth-history", response_model=NetWorthHistoryResponse)
def get_net_worth_history(
    period: str = Query(default="6m"),
    base_currency: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NetWorthHistoryResponse:
    return AnalyticsService(db).net_worth_history(current_user.id, period, base_currency)


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    wallet_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    return AnalyticsService(db).forecast_month_end_balance(current_user.id, wallet_id)


@router.get("/balance-history", response_model=BalanceHistoryResponse)
def get_balance_history(
    date_from: date = Query(...),
    date_to: date = Query(...),
    wallet_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BalanceHistoryResponse:
    return AnalyticsService(db).wallet_balance_history(current_user.id, wallet_id, date_from, date_to)


@router.get("/insights", response_model=list[AIInsightPublic])
def get_insights(
    refresh: bool = Query(default=False),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    locale: str = Depends(get_locale),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIInsightPublic]:
    """Lazily regenerates (Azure call + AnalyticsService.spending_recommendations())
    only when this user's cached insights are missing or older than
    ai.personal_finance.insights.INSIGHT_TTL - see that module's docstring.
    refresh=True (the dashboard's refresh button) bypasses the TTL.

    year/month (the app-wide month selector, same convention as
    spending-by-type/spending-by-category) score against the end of that
    month instead of live now — get_or_generate() detects whether that's
    still the real current month (TTL-cached, refreshes live) or a closed
    past month (generated once, cached forever, since its figures can't
    change). Omit both for the current month.

    A regeneration narrates in the site's current language (X-Locale
    header, see ai/locale.py) — a cached row keeps whatever language it
    was generated in until it's regenerated."""
    as_of = _end_of_month(year, month) if year is not None or month is not None else None
    result = ai_insights.get_or_generate(db, current_user.id, force=refresh, locale=locale, as_of=as_of)
    db.commit()
    return result


def _end_of_month(year: int | None, month: int | None) -> datetime:
    if (year is None) != (month is None):
        raise ValidationError("year and month must be provided together")
    if not 1 <= month <= 12:
        raise ValidationError("month must be between 1 and 12")
    days_in_month = calendar.monthrange(year, month)[1]
    return datetime(year, month, days_in_month, 23, 59, 59, 999999, tzinfo=timezone.utc)


@router.post("/insights/{insight_id}/dismiss", status_code=204)
def dismiss_insight(
    insight_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ai_insights.dismiss(db, current_user.id, insight_id)
    db.commit()
