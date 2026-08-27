"""Pydantic schemas for the savings module."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.savings.models import SavingsGoalStatus


class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    currency: str = "RON"
    target_date: date | None = None
    initial_amount: Decimal = Decimal("0")


class SavingsContribution(BaseModel):
    wallet_id: uuid.UUID
    # Amount to debit, in the selected wallet's own currency. Same-currency
    # as the goal: this is exactly what the goal's current_amount grows by.
    # Cross-currency: fx_quote_id is required (from POST /fx/quote, same
    # mechanism cross-currency IBAN transfers use) and the goal grows by
    # the quote's target_amount instead.
    amount: Decimal
    fx_quote_id: uuid.UUID | None = None


class SavingsWithdrawal(BaseModel):
    wallet_id: uuid.UUID
    fx_quote_id: uuid.UUID | None = None


class SavingsGoalDeleteRequest(BaseModel):
    # Only required when the goal still has money in it (current_amount >
    # 0) - deleting it then withdraws to this wallet first, same as a
    # regular withdrawal, so nothing is lost. Not required for an
    # already-empty (fully withdrawn) goal.
    wallet_id: uuid.UUID | None = None
    fx_quote_id: uuid.UUID | None = None


class SavingsGoalPublic(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal
    currency: str
    target_date: date | None
    status: SavingsGoalStatus
    percent_complete: float
    monthly_amount_needed: Decimal | None
    created_at: datetime
