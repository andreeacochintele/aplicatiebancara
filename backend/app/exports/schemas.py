"""Pydantic schemas for the business transaction export (architecture.md §25)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.transactions.models import TransactionStatus, TransactionType


class TransactionExportRequest(BaseModel):
    date_from: date
    date_to: date
    wallet_id: uuid.UUID | None = None
    currency: str | None = None
    direction: Literal["incoming", "outgoing"] | None = None
    status: TransactionStatus | None = None
    category_id: uuid.UUID | None = None


class ExportedTransaction(BaseModel):
    date: datetime
    transaction_id: uuid.UUID
    type: TransactionType
    counterparty: str
    description: str | None
    amount: Decimal
    currency: str
    status: TransactionStatus
