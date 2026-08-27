"""Pydantic schemas for the credit module."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.credit.models import (
    CreditApplicationStatus,
    CreditApplicationType,
    CreditDocumentPurpose,
    CreditDocumentStatus,
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
    source_wallet_id: uuid.UUID | None = None
    amount: Decimal
    source_card_id: uuid.UUID | None = None


class RegularInstallmentPaymentRequest(BaseModel):
    source_wallet_id: uuid.UUID | None = None
    source_card_id: uuid.UUID | None = None


class LoanAutopayUpdate(BaseModel):
    enabled: bool
    amount: Decimal | None = None
    source_wallet_id: uuid.UUID | None = None
    source_card_id: uuid.UUID | None = None
    next_run_on: date | None = None


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


class RegularInstallmentPaymentResult(BaseModel):
    loan_id: uuid.UUID
    installment_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    fees_paid: Decimal
    remaining_principal: Decimal
    next_payment_date: date | None
    loan_status: LoanStatus


class CreditApplicationDocumentCreate(BaseModel):
    document_type: str
    file_name: str
    content_type: str | None = None
    file_size: int
    content_base64: str | None = None


class CreditApplicationCreate(BaseModel):
    type: CreditApplicationType
    loan_product_type: LoanProductType | None = LoanProductType.PERSONAL_LOAN
    requested_amount: Decimal
    currency: str = "RON"
    requested_term_months: int | None = None
    documents: list[CreditApplicationDocumentCreate] | None = None


class CreditDocumentCreate(BaseModel):
    application_id: uuid.UUID | None = None
    purpose: CreditDocumentPurpose
    document_type: str
    file_name: str
    content_type: str | None = None
    file_size: int
    content_base64: str | None = None


class CreditDocumentReview(BaseModel):
    status: CreditDocumentStatus
    evaluation_score: int | None = None
    review_note: str | None = None


class CreditDocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    application_id: uuid.UUID | None
    purpose: CreditDocumentPurpose
    document_type: str
    file_name: str
    content_type: str | None
    file_size: int
    status: CreditDocumentStatus
    evaluation_score: int | None
    review_note: str | None
    uploaded_at: datetime
    reviewed_at: datetime | None
    reviewed_by_admin_id: uuid.UUID | None


class CreditDocumentContentPublic(BaseModel):
    id: uuid.UUID
    file_name: str
    content_type: str | None
    content_base64: str


class LoanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    application_id: uuid.UUID
    loan_product_type: LoanProductType | None = None
    principal_amount: Decimal
    currency: str
    interest_rate: Decimal
    term_months: int
    monthly_payment: Decimal
    outstanding_principal: Decimal
    start_date: date
    maturity_date: date
    next_payment_date: date
    autopay_enabled: bool = False
    autopay_source_wallet_id: uuid.UUID | None = None
    autopay_source_card_id: uuid.UUID | None = None
    autopay_next_run_on: date | None = None
    autopay_amount: Decimal | None = None
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
    documents: list[CreditDocumentPublic] = []
