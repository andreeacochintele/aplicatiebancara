"""Pydantic schemas for the cards module."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.cards.models import CardFreezeReason, CardStatus, CardTier, CardType


class CardCreate(BaseModel):
    type: CardType = CardType.DEBIT
    tier: CardTier | None = None
    default_wallet_id: uuid.UUID | None = None
    new_wallet_currency: str | None = None
    currency: str | None = None
    collateral_wallet_id: uuid.UUID | None = None
    collateral_amount: Decimal | None = None


class CreditCardAccountPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card_id: uuid.UUID
    user_id: uuid.UUID
    currency: str
    credit_limit: Decimal
    used_amount: Decimal
    available_credit: Decimal
    annual_interest_rate: Decimal
    collateral_wallet_id: uuid.UUID | None = None
    collateral_amount: Decimal | None = Decimal("0.00")
    updated_at: datetime


class CardPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    default_wallet_id: uuid.UUID | None
    type: CardType
    tier: CardTier | None
    status: CardStatus
    freeze_reason: CardFreezeReason | None = None
    frozen_at: datetime | None = None
    masked_pan: str
    last_four: str
    mock_pan: str
    mock_cvv: str
    has_pin: bool = False
    expiration_month: int
    expiration_year: int
    one_time_remaining: int | None
    credit_account: CreditCardAccountPublic | None = None
    created_at: datetime
    updated_at: datetime


class CardPinUpdate(BaseModel):
    pin: str


class CardRevealRequest(BaseModel):
    pin: str


class CardSensitiveDetails(BaseModel):
    card_id: uuid.UUID
    mock_pan: str
    mock_cvv: str


class CardPaymentPreferencesUpdate(BaseModel):
    preferred_wallet_id: uuid.UUID | None = None
    allow_main_wallet_fx: bool = False


class CardPaymentPreferencesPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card_id: uuid.UUID
    preferred_wallet_id: uuid.UUID | None
    allow_main_wallet_fx: bool
    updated_at: datetime
