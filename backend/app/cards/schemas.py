"""Pydantic schemas for the cards module."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.cards.models import CardStatus, CardTier, CardType


class CardCreate(BaseModel):
    type: CardType = CardType.DEBIT
    tier: CardTier | None = None
    default_wallet_id: uuid.UUID | None = None


class CardPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    default_wallet_id: uuid.UUID | None
    type: CardType
    tier: CardTier | None
    status: CardStatus
    masked_pan: str
    last_four: str
    mock_pan: str
    mock_cvv: str
    expiration_month: int
    expiration_year: int
    one_time_remaining: int | None
    created_at: datetime
    updated_at: datetime


class CardPaymentPreferencesUpdate(BaseModel):
    preferred_wallet_id: uuid.UUID | None = None
    allow_main_wallet_fx: bool = False


class CardPaymentPreferencesPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card_id: uuid.UUID
    preferred_wallet_id: uuid.UUID | None
    allow_main_wallet_fx: bool
    updated_at: datetime
