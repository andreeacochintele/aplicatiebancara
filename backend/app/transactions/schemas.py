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


class TransactionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    initiator_user_id: uuid.UUID
    source_wallet_id: uuid.UUID | None
    destination_wallet_id: uuid.UUID | None
    type: TransactionType
    status: TransactionStatus
    amount: Decimal
    currency: str
    description: str | None
    created_at: datetime
    completed_at: datetime | None
