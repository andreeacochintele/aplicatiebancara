"""Analytics endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics.schemas import ForecastResponse, MonthlyTrendResponse, NetWorthResponse, SpendingByTypeResponse
from app.analytics.service import AnalyticsService
from app.auth.dependencies import get_current_user
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


@router.get("/monthly-trend", response_model=MonthlyTrendResponse)
def get_monthly_trend(
    months: int = Query(default=6),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonthlyTrendResponse:
    return AnalyticsService(db).monthly_trend(current_user.id, months)


@router.get("/net-worth", response_model=NetWorthResponse)
def get_net_worth(
    base_currency: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NetWorthResponse:
    return AnalyticsService(db).net_worth(current_user.id, base_currency)


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    wallet_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    return AnalyticsService(db).forecast_month_end_balance(current_user.id, wallet_id)
