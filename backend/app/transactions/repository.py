"""Data-access layer for Transaction and WalletLedgerEntry."""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.transactions.models import Transaction, WalletLedgerEntry
from app.wallets.models import Wallet


class TransactionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        if is_supabase_session(self.db):
            return self.db.get(Transaction, transaction_id)
        return self.db.get(Transaction, transaction_id)

    def get_for_user(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction | None:
        if is_supabase_session(self.db):
            transaction = self.db.get(Transaction, transaction_id)
            if transaction is None:
                return None
            wallet_ids = {wallet.id for wallet in self.db.fetch_many(Wallet, {"user_id": f"eq.{user_id}", "select": "id"})}
            if (
                transaction.initiator_user_id == user_id
                or transaction.source_wallet_id in wallet_ids
                or transaction.destination_wallet_id in wallet_ids
            ):
                return transaction
            return None
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
        if is_supabase_session(self.db):
            wallets = self.db.fetch_many(Wallet, {"user_id": f"eq.{user_id}", "select": "id"})
            wallet_ids = [str(wallet.id) for wallet in wallets]
            clauses = [f"initiator_user_id.eq.{user_id}"]
            if wallet_ids:
                joined = ",".join(wallet_ids)
                clauses.extend([f"source_wallet_id.in.({joined})", f"destination_wallet_id.in.({joined})"])
            return self.db.fetch_many(
                Transaction,
                {
                    "or": f"({','.join(clauses)})",
                    "order": "created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
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
        if is_supabase_session(self.db):
            return self.db.add(transaction)
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def add_ledger_entry(self, entry: WalletLedgerEntry) -> WalletLedgerEntry:
        if is_supabase_session(self.db):
            return self.db.add(entry)
        self.db.add(entry)
        self.db.flush()
        return entry
