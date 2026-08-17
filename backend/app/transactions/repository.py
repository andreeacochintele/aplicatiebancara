"""Data-access layer for Transaction and WalletLedgerEntry."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.transactions.models import Transaction, WalletLedgerEntry


class TransactionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        return self.db.get(Transaction, transaction_id)

    def list_for_user(self, user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[Transaction]:
        stmt = (
            select(Transaction)
            .where(Transaction.initiator_user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def add(self, transaction: Transaction) -> Transaction:
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def add_ledger_entry(self, entry: WalletLedgerEntry) -> WalletLedgerEntry:
        self.db.add(entry)
        self.db.flush()
        return entry
