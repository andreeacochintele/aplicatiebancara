"""Pydantic schemas for the savings module."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    currency: str = "RON"
    target_date: date | None = None
    initial_amount: Decimal = Decimal("0")


class SavingsContribution(BaseModel):
    amount: Decimal


class SavingsGoalPublic(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal
    currency: str
    target_date: date | None
    percent_complete: float
    monthly_amount_needed: Decimal | None
    created_at: datetime
