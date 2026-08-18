"""Pydantic schemas for payment beneficiaries."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.payments.models import PaymentRequestStatus, ScheduledPaymentFrequency, ScheduledPaymentStatus


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
