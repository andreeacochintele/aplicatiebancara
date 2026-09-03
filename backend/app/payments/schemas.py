"""Pydantic schemas for payment beneficiaries."""
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.payments.models import (
    BillSplitParticipantStatus,
    BillSplitStatus,
    PaymentRequestStatus,
    ScheduledPaymentFrequency,
    ScheduledPaymentStatus,
)


class BeneficiaryCreate(BaseModel):
    beneficiary_user_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    iban: str | None = Field(default=None, max_length=34)
    phone: str | None = Field(default=None, max_length=32)
    is_favorite: bool = False

    @model_validator(mode="after")
    def require_payment_target(self) -> "BeneficiaryCreate":
        if not any([self.beneficiary_user_id, self.iban, self.phone]):
            raise ValueError("Beneficiary requires beneficiary_user_id, iban or phone")
        return self


class BeneficiaryUpdate(BaseModel):
    beneficiary_user_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    iban: str | None = Field(default=None, max_length=34)
    phone: str | None = Field(default=None, max_length=32)
    is_favorite: bool | None = None


class BeneficiaryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    beneficiary_user_id: uuid.UUID | None
    name: str
    iban: str | None
    phone: str | None
    is_favorite: bool
    created_at: datetime


class IbanTransferCreate(BaseModel):
    beneficiary_name: str = Field(min_length=1, max_length=255)
    iban: str = Field(min_length=1, max_length=34)
    # Only sent for accounts that are not IBANs (countries outside the ISO
    # 13616 registry), where a BIC is what makes the payment routable. There
    # is no column for it — the service folds it into the description, so it
    # still shows up on the statement and the payment confirmation.
    bic: str | None = Field(default=None, min_length=8, max_length=11)
    source_wallet_id: uuid.UUID
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=500)
    save_beneficiary: bool = False
    is_favorite: bool = False
    fx_quote_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_amount(self) -> "IbanTransferCreate":
        if self.amount <= 0:
            raise ValueError("Transfer amount must be positive")
        return self


class BulkTransferRow(BaseModel):
    beneficiary_name: str = Field(min_length=1, max_length=255)
    iban: str = Field(min_length=1, max_length=34)
    amount: Decimal
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_amount(self) -> "BulkTransferRow":
        if self.amount <= 0:
            raise ValueError("Transfer amount must be positive")
        return self


class BulkTransferCreate(BaseModel):
    source_wallet_id: uuid.UUID
    currency: str = Field(min_length=3, max_length=3)
    rows: list[BulkTransferRow] = Field(min_length=1, max_length=200)
    save_beneficiaries: bool = False


class BulkTransferRowResult(BaseModel):
    beneficiary_name: str
    iban: str
    amount: Decimal
    transaction_id: uuid.UUID | None = None
    status: str | None = None
    error: str | None = None


class BulkTransferResult(BaseModel):
    succeeded: int
    failed: int
    results: list[BulkTransferRowResult]


class BulkTransferBatchSummary(BaseModel):
    batch_reference: str
    created_at: datetime
    currency: str
    total_amount: Decimal
    row_count: int
    completed_count: int
    pending_review_count: int
    other_count: int


class BulkTransferExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class BulkTransferExtractedRow(BaseModel):
    beneficiary_name: str
    iban: str
    amount: str
    description: str | None


class BulkTransferTemplateRowCreate(BaseModel):
    beneficiary_name: str = Field(min_length=1, max_length=255)
    iban: str = Field(min_length=1, max_length=34)
    amount: Decimal
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_amount(self) -> "BulkTransferTemplateRowCreate":
        if self.amount <= 0:
            raise ValueError("Row amount must be positive")
        return self


class BulkTransferTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_wallet_id: uuid.UUID
    currency: str = Field(min_length=3, max_length=3)
    frequency: ScheduledPaymentFrequency
    next_run_on: date
    rows: list[BulkTransferTemplateRowCreate] = Field(min_length=1, max_length=200)


class BulkTransferTemplateStatusUpdate(BaseModel):
    status: ScheduledPaymentStatus


class BulkTransferTemplateRowPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    beneficiary_name: str
    iban: str
    amount: Decimal
    description: str | None


class BulkTransferTemplatePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    source_wallet_id: uuid.UUID
    name: str
    currency: str
    frequency: ScheduledPaymentFrequency
    next_run_on: date
    status: ScheduledPaymentStatus
    created_at: datetime
    updated_at: datetime
    rows: list[BulkTransferTemplateRowPublic]


class IbanTransferQuoteCreate(BaseModel):
    source_wallet_id: uuid.UUID
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_amount(self) -> "IbanTransferQuoteCreate":
        if self.amount <= 0:
            raise ValueError("Transfer amount must be positive")
        return self


class PhoneLookupRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=32)


class PhoneRecipientPreview(BaseModel):
    user_id: uuid.UUID
    first_name: str
    last_name: str
    phone: str
    destination_wallet_id: uuid.UUID
    destination_wallet_currency: str


class PhoneTransferCreate(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    source_wallet_id: uuid.UUID
    amount: Decimal
    description: str | None = None


class PaymentRequestCreate(BaseModel):
    destination_wallet_id: uuid.UUID
    amount: Decimal | None = None
    currency: str = Field(min_length=3, max_length=3)
    expires_in_minutes: int = Field(default=15, ge=1, le=1440)
    # Purely descriptive, shown back to the payer — see PaymentRequest model
    # docstring. Optional for everyone; a business "invoice" is this same
    # request with these two filled in, not a separate flow.
    reference: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_amount(self) -> "PaymentRequestCreate":
        if self.amount is not None and self.amount <= 0:
            raise ValueError("Payment request amount must be positive")
        return self


class PaymentRequestPay(BaseModel):
    source_wallet_id: uuid.UUID
    amount: Decimal | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_amount(self) -> "PaymentRequestPay":
        if self.amount is not None and self.amount <= 0:
            raise ValueError("Payment amount must be positive")
        return self


class PaymentRequestPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creator_user_id: uuid.UUID
    destination_wallet_id: uuid.UUID
    amount: Decimal | None
    currency: str
    status: PaymentRequestStatus
    expires_at: datetime
    created_at: datetime
    reference: str | None
    note: str | None


class ScheduledPaymentCreate(BaseModel):
    beneficiary_name: str = Field(min_length=1, max_length=255)
    iban: str = Field(min_length=1, max_length=34)
    source_wallet_id: uuid.UUID
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    frequency: ScheduledPaymentFrequency
    next_run_on: date
    notify_days_before: int = Field(default=0, ge=0, le=30)
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_amount(self) -> "ScheduledPaymentCreate":
        if self.amount <= 0:
            raise ValueError("Scheduled payment amount must be positive")
        return self


class ScheduledPaymentUpdate(BaseModel):
    beneficiary_name: str | None = Field(default=None, min_length=1, max_length=255)
    iban: str | None = Field(default=None, min_length=1, max_length=34)
    source_wallet_id: uuid.UUID | None = None
    amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    frequency: ScheduledPaymentFrequency | None = None
    next_run_on: date | None = None
    notify_days_before: int | None = Field(default=None, ge=0, le=30)
    status: ScheduledPaymentStatus | None = None
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_amount(self) -> "ScheduledPaymentUpdate":
        if self.amount is not None and self.amount <= 0:
            raise ValueError("Scheduled payment amount must be positive")
        return self


class ScheduledPaymentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    source_wallet_id: uuid.UUID
    beneficiary_name: str
    iban: str
    amount: Decimal
    currency: str
    frequency: ScheduledPaymentFrequency
    next_run_on: date
    notify_days_before: int
    status: ScheduledPaymentStatus
    description: str | None
    created_at: datetime
    updated_at: datetime


class BillSplitParticipantCreate(BaseModel):
    participant_user_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    amount: Decimal | None = None
    percent: Decimal | None = None

    @model_validator(mode="after")
    def validate_amount_and_target(self) -> "BillSplitParticipantCreate":
        if self.amount is None and self.percent is None:
            raise ValueError("Participant requires amount or percent")
        if self.amount is not None and self.amount <= 0:
            raise ValueError("Participant amount must be positive")
        if self.percent is not None and (self.percent <= 0 or self.percent > 100):
            raise ValueError("Participant percent must be between 0 and 100")
        if self.participant_user_id is None and self.phone is None:
            raise ValueError("Participant requires participant_user_id or phone")
        return self


class BillSplitCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    total_amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    source_transaction_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    participants: list[BillSplitParticipantCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_total(self) -> "BillSplitCreate":
        if self.total_amount <= 0:
            raise ValueError("Bill split total amount must be positive")
        participants_total = Decimal("0")
        for participant in self.participants:
            if participant.amount is None and participant.percent is not None:
                participant.amount = (self.total_amount * participant.percent / Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            if participant.amount is None:
                raise ValueError("Participant amount is required")
            participants_total += participant.amount
        if participants_total > self.total_amount:
            raise ValueError("Participant amounts cannot exceed the total amount")
        return self


class BillSplitParticipantPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_split_id: uuid.UUID
    participant_user_id: uuid.UUID | None
    name: str
    phone: str | None
    amount: Decimal
    status: BillSplitParticipantStatus
    paid_transaction_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class BillSplitPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    source_transaction_id: uuid.UUID | None
    title: str
    total_amount: Decimal
    currency: str
    status: BillSplitStatus
    description: str | None
    created_at: datetime
    updated_at: datetime
    participants: list[BillSplitParticipantPublic]


class BillSplitPay(BaseModel):
    source_wallet_id: uuid.UUID
    description: str | None = Field(default=None, max_length=500)


class TransactionFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=500)


class TransactionFolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=500)


class TransactionFolderItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    folder_id: uuid.UUID
    transaction_id: uuid.UUID
    added_at: datetime


class TransactionFolderPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    color: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    items: list[TransactionFolderItemPublic] = []


class TransactionFolderAddTransaction(BaseModel):
    transaction_id: uuid.UUID
