"""Analytics endpoints, scoped to the authenticated user."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics.schemas import MonthlyTrendResponse, SpendingByTypeResponse
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
