"""Pydantic schemas for the analytics module."""
import uuid
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


class MonthlyTrendTotal(BaseModel):
    """One month's spend across all currencies, converted to base_currency —
    the FX-comparable series the trend chart plots by default."""

    year: int
    month: int
    total_amount: Decimal


class MonthlyTrendResponse(BaseModel):
    base_currency: str
    items: list[MonthlyTrendItem]
    totals_by_month: list[MonthlyTrendTotal]


class WalletBalanceItem(BaseModel):
    wallet_id: uuid.UUID
    currency: str
    available_balance: Decimal
    reserved_balance: Decimal
    is_main: bool
    converted_available_balance: Decimal


class NetWorthResponse(BaseModel):
    base_currency: str
    total_available_balance: Decimal
    wallets: list[WalletBalanceItem]


class ForecastPoint(BaseModel):
    date: date
    projected_balance: Decimal


class ForecastResponse(BaseModel):
    wallet_id: uuid.UUID
    currency: str
    current_balance: Decimal
    days_elapsed: int
    days_remaining: int
    average_daily_net_change: Decimal
    projected_month_end_balance: Decimal
    projected_series: list[ForecastPoint]
    note: str


class NetWorthHistoryPoint(BaseModel):
    date: date
    value: Decimal


class NetWorthHistoryResponse(BaseModel):
    base_currency: str
    history: list[NetWorthHistoryPoint]
    note: str
