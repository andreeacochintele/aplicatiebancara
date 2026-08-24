"""Pydantic schemas for the credit module."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.credit.models import (
    CreditApplicationStatus,
    CreditApplicationType,
    LoanInstallmentStatus,
    LoanProductType,
    LoanStatus,
)


class CreditProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    current_score: int
    income: Decimal
    existing_debt: Decimal
    currency: str
    updated_at: datetime


class CreditScoreRecalculateRequest(BaseModel):
    income: Decimal | None = None
    existing_debt: Decimal | None = None
    currency: str | None = None


class CreditScorePublic(BaseModel):
    score: int
    band: str
    reason_data: dict[str, Any]
    calculated_at: datetime


class CreditApplicationCreate(BaseModel):
    type: CreditApplicationType
    loan_product_type: LoanProductType | None = LoanProductType.PERSONAL_LOAN
    requested_amount: Decimal
    currency: str = "RON"
    requested_term_months: int | None = None


class LoanProductPublic(BaseModel):
    product_type: LoanProductType
    name: str
    description: str
    representative_apr: Decimal
    borrowing_rate_note: str
    typical_term_months: str
    fees: list[str]
    obligations: list[str]
    liabilities: list[str]
    required_documents: list[str]
    collateral_required: bool
    insurance_required: bool


class CreditApplicationDecision(BaseModel):
    status: CreditApplicationStatus
    offered_amount: Decimal | None = None
    offered_interest_rate: Decimal | None = None


class LoanCalculatorRequest(BaseModel):
    principal_amount: Decimal
    currency: str = "RON"
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
    currency: str
    annual_interest_rate: Decimal
    term_months: int
    monthly_payment: Decimal
    total_payment: Decimal
    total_interest: Decimal
    schedule: list[LoanInstallmentPreview]


class EarlyRepaymentSimulationRequest(BaseModel):
    extra_payment_amount: Decimal


class EarlyRepaymentPaymentRequest(BaseModel):
    source_wallet_id: uuid.UUID
    amount: Decimal
    source_card_id: uuid.UUID | None = None


class EarlyRepaymentResult(BaseModel):
    loan_id: uuid.UUID
    currency: str
    original_outstanding_principal: Decimal
    extra_payment_amount: Decimal
    applied_extra_payment_amount: Decimal
    new_outstanding_principal: Decimal
    remaining_term_months: int
    revised_term_months: int
    term_months_reduced: int
    total_interest_before: Decimal
    total_interest_after: Decimal
    total_interest_saved: Decimal


class EarlyRepaymentPaymentResult(EarlyRepaymentResult):
    transaction_id: uuid.UUID
    loan_status: LoanStatus


class LoanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    application_id: uuid.UUID
    principal_amount: Decimal
    currency: str
    interest_rate: Decimal
    term_months: int
    monthly_payment: Decimal
    outstanding_principal: Decimal
    start_date: date
    maturity_date: date
    next_payment_date: date
    status: LoanStatus
    created_at: datetime
    closed_at: datetime | None


class LoanInstallmentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_id: uuid.UUID
    installment_number: int
    due_date: date
    payment_amount: Decimal
    principal_amount: Decimal
    interest_amount: Decimal
    fees_amount: Decimal
    remaining_principal: Decimal
    status: LoanInstallmentStatus


class CreditApplicationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: CreditApplicationType
    loan_product_type: LoanProductType | None
    requested_amount: Decimal
    currency: str
    requested_term_months: int | None
    offered_interest_rate: Decimal | None
    offered_amount: Decimal | None
    credit_score_at_application: int
    status: CreditApplicationStatus
    created_at: datetime
    resolved_at: datetime | None
