"""Pydantic schemas for the budgets module."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.budgets.models import BudgetPeriod


class BudgetCreate(BaseModel):
    name: str
    limit_amount: Decimal
    currency: str = "RON"
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    category: str | None = None


class BudgetPublic(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None
    limit_amount: Decimal
    currency: str
    period: BudgetPeriod
    spent_amount: Decimal
    percent_used: float
    remaining_amount: Decimal
    period_end: date
    days_remaining: int
    created_at: datetime
