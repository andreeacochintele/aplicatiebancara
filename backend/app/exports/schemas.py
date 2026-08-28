"""Pydantic schemas for the business transaction export (architecture.md §25)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.exports.models import ExportFormat, ExportStatus, ExportType
from app.transactions.models import TransactionStatus, TransactionType

ExportFileFormat = Literal["csv", "xlsx", "pdf", "mt940"]


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
    category: str | None
    direction: Literal["IN", "OUT"]
    amount: Decimal
    currency: str
    status: TransactionStatus


class ExportCurrencyTotal(BaseModel):
    currency: str
    total_incoming: Decimal
    total_outgoing: Decimal


class TransactionExportPreview(BaseModel):
    date_from: date
    date_to: date
    row_count: int
    totals: list[ExportCurrencyTotal]
    transactions: list[ExportedTransaction]


class ExportJobPublic(BaseModel):
    id: uuid.UUID
    type: ExportType
    format: ExportFormat
    date_from: date
    date_to: date
    status: ExportStatus
    row_count: int
    created_at: datetime
