"""Pydantic schemas for the credit module."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.credit.models import CreditApplicationStatus, CreditApplicationType


class CreditProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    current_score: int
    income: Decimal
    existing_debt: Decimal
    updated_at: datetime


class CreditScoreRecalculateRequest(BaseModel):
    income: Decimal | None = None
    existing_debt: Decimal | None = None


class CreditScorePublic(BaseModel):
    score: int
    band: str
    reason_data: dict[str, Any]
    calculated_at: datetime


class CreditApplicationCreate(BaseModel):
    type: CreditApplicationType
    requested_amount: Decimal
    requested_term_months: int | None = None


class LoanCalculatorRequest(BaseModel):
    principal_amount: Decimal
    annual_interest_rate: Decimal
    term_months: int


class LoanInstallmentPreview(BaseModel):
    installment_number: int
    payment_amount: Decimal
    principal_amount: Decimal
    interest_amount: Decimal
    remaining_principal: Decimal


class LoanCalculatorResult(BaseModel):
    principal_amount: Decimal
    annual_interest_rate: Decimal
    term_months: int
    monthly_payment: Decimal
    total_payment: Decimal
    total_interest: Decimal
    schedule: list[LoanInstallmentPreview]


class CreditApplicationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: CreditApplicationType
    requested_amount: Decimal
    requested_term_months: int | None
    offered_interest_rate: Decimal | None
    offered_amount: Decimal | None
    credit_score_at_application: int
    status: CreditApplicationStatus
    created_at: datetime
    resolved_at: datetime | None
