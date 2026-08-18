"""Data-access layer for statement generation — reads WalletLedgerEntry, the
ledger of truth for balances (architecture.md §7), joined to its Transaction
for the human-readable description/type/status."""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

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
