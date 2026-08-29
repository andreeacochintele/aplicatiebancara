"""Pydantic schemas for the transactions module."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.transactions.models import TransactionStatus, TransactionType


class InternalTransferCreate(BaseModel):
    source_wallet_id: uuid.UUID
    destination_wallet_id: uuid.UUID
    amount: Decimal
    description: str | None = None
    # Required only when source_wallet.currency != destination_wallet.currency —
    # obtain one first via POST /fx/quote.
    fx_quote_id: uuid.UUID | None = None


class CardPaymentCreate(BaseModel):
    card_id: uuid.UUID
    merchant_id: uuid.UUID
    amount: Decimal
    cvv: str
    description: str | None = None


class CreditCardRepaymentCreate(BaseModel):
    card_id: uuid.UUID
    source_wallet_id: uuid.UUID
    amount: Decimal


class CardTopUpCreate(BaseModel):
    destination_wallet_id: uuid.UUID
    card_number: str
    cardholder_name: str
    expiry_month: int
    expiry_year: int
    cvv: str
    amount: Decimal


class TransactionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    initiator_user_id: uuid.UUID
    source_wallet_id: uuid.UUID | None
    destination_wallet_id: uuid.UUID | None
    card_id: uuid.UUID | None
    type: TransactionType
    status: TransactionStatus
    amount: Decimal
    currency: str
    source_amount: Decimal | None
    source_currency: str | None
    exchange_rate: Decimal | None
    description: str | None
    created_at: datetime
    completed_at: datetime | None
    # Spending category, resolved per transactions/categories.py: the user's
    # own choice if they re-filed this one, else the merchant's category,
    # else "Other". Card payments only — null on everything else, since a
    # transfer has no merchant and is counted by no category view.
    # `category_id` is null whenever the category shown is the merchant's
    # rather than a deliberate choice — that is what the picker uses to tell
    # "inherited" from "overridden".
    category: str | None = None
    category_id: uuid.UUID | None = None


class TransactionCategoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class TransactionCategoryUpdate(BaseModel):
    # Null clears the override, falling the transaction back to its
    # merchant's category.
    category_id: uuid.UUID | None = None
