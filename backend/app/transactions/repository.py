"""Data-access layer for Transaction and WalletLedgerEntry."""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.transactions.models import Transaction, WalletLedgerEntry
from app.wallets.models import Wallet


class TransactionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        return self.db.get(Transaction, transaction_id)

    def get_for_user(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction | None:
        user_wallet_ids = select(Wallet.id).where(Wallet.user_id == user_id)
        stmt = select(Transaction).where(
            Transaction.id == transaction_id,
            or_(
                Transaction.initiator_user_id == user_id,
                Transaction.source_wallet_id.in_(user_wallet_ids),
                Transaction.destination_wallet_id.in_(user_wallet_ids),
            ),
        )
        return self.db.scalar(stmt)

    def list_for_user(self, user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[Transaction]:
        user_wallet_ids = select(Wallet.id).where(Wallet.user_id == user_id)
        stmt = (
            select(Transaction)
            .where(
                or_(
                    Transaction.initiator_user_id == user_id,
                    Transaction.source_wallet_id.in_(user_wallet_ids),
                    Transaction.destination_wallet_id.in_(user_wallet_ids),
                )
            )
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
