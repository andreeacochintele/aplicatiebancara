"""Pydantic schemas for the analytics module."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.transactions.models import TransactionType


class SpendingByType(BaseModel):
    type: TransactionType
    total_amount: Decimal
    currency: str
    transaction_count: int


class SpendingByTypeResponse(BaseModel):
    period_start: date
    period_end: date
    items: list[SpendingByType]


class MonthlyTrendItem(BaseModel):
    year: int
    month: int
    currency: str
    total_amount: Decimal
    transaction_count: int


class MonthlyTrendResponse(BaseModel):
    items: list[MonthlyTrendItem]
