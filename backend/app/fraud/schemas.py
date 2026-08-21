"""Pydantic schemas for the fraud module."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.fraud.models import FraudCaseStatus, FraudFlagCode


class FraudFlagPublic(BaseModel):
    id: uuid.UUID
    code: FraudFlagCode
    points: Decimal
    description: str


class FraudCaseSummary(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    user_id: uuid.UUID
    risk_score: Decimal
    status: FraudCaseStatus
    hold_amount: Decimal
    created_at: datetime
    flag_codes: list[FraudFlagCode]


class FraudCaseDetail(FraudCaseSummary):
    decided_by_admin_id: uuid.UUID | None
    decided_at: datetime | None
    flags: list[FraudFlagPublic]
    transaction_amount: Decimal
    transaction_currency: str
    transaction_description: str | None
    transaction_created_at: datetime


class FraudDecisionRequest(BaseModel):
    action: Literal["APPROVE", "REJECT"]
