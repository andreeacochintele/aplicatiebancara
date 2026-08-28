"""Pydantic schemas for the statements module (architecture.md §24)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.transactions.models import TransactionStatus, TransactionType


class StatementRequest(BaseModel):
    wallet_id: uuid.UUID
    date_from: date
    date_to: date
    transaction_type: TransactionType | None = None


class StatementTransaction(BaseModel):
    id: uuid.UUID
    created_at: datetime
    type: TransactionType
    status: TransactionStatus
    description: str | None
    direction: str
    amount: Decimal


class StatementPublic(BaseModel):
    wallet_id: uuid.UUID
    iban: str
    account_holder_name: str
    representative_name: str | None = None
    currency: str
    date_from: date
    date_to: date
    opening_balance: Decimal
    closing_balance: Decimal
    total_incoming: Decimal
    total_outgoing: Decimal
    transactions: list[StatementTransaction]
