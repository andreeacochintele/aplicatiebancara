"""Data-access layer for statement generation — reads WalletLedgerEntry, the
ledger of truth for balances (architecture.md §7), joined to its Transaction
for the human-readable description/type/status."""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.supabase import is_supabase_session
from app.transactions.models import Transaction, TransactionType, WalletLedgerEntry


class StatementRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_entries(
        self,
        wallet_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        transaction_type: TransactionType | None = None,
    ) -> list[WalletLedgerEntry]:
        if is_supabase_session(self.db):
            entries = self.db.fetch_many(
                WalletLedgerEntry,
                {
                    "wallet_id": f"eq.{wallet_id}",
                    "and": f"(created_at.gte.{period_start.isoformat()},created_at.lte.{period_end.isoformat()})",
                    "order": "created_at.asc",
                },
            )
            if not entries:
                return []

            transaction_ids = ",".join(str(entry.transaction_id) for entry in entries)
            transactions = self.db.fetch_many(Transaction, {"id": f"in.({transaction_ids})"})
            by_id = {transaction.id: transaction for transaction in transactions}

            hydrated_entries = []
            for entry in entries:
                transaction = by_id.get(entry.transaction_id)
                if transaction is None:
                    continue
                if transaction_type is not None and transaction.type != transaction_type:
                    continue
                entry.transaction = transaction
                hydrated_entries.append(entry)
            return hydrated_entries

        stmt = (
            select(WalletLedgerEntry)
            .join(Transaction, WalletLedgerEntry.transaction_id == Transaction.id)
            .where(
                WalletLedgerEntry.wallet_id == wallet_id,
                WalletLedgerEntry.created_at >= period_start,
                WalletLedgerEntry.created_at <= period_end,
            )
            .options(joinedload(WalletLedgerEntry.transaction))
            .order_by(WalletLedgerEntry.created_at)
        )
        if transaction_type is not None:
            stmt = stmt.where(Transaction.type == transaction_type)
        return list(self.db.scalars(stmt))
