"""Data-access layer for the business transaction export — reads
WalletLedgerEntry (architecture.md §7's source of truth for wallet activity)
across every wallet a user owns, joined to Transaction. Extends
statements/repository.py's single-wallet StatementRepository.list_entries
pattern to span all of a business user's wallets, narrowed by an optional
wallet_id plus the filters architecture.md §25 lists (currency,
incoming/outgoing, status, category)."""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.exports.models import ExportJob
from app.supabase import is_supabase_session
from app.transactions.models import LedgerEntryType, Transaction, TransactionCategory, TransactionStatus, WalletLedgerEntry
from app.wallets.models import Wallet

_ENTRY_TYPES_BY_DIRECTION = {
    "incoming": LedgerEntryType.CREDIT,
    "outgoing": LedgerEntryType.DEBIT,
}


class ExportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_entries_for_user(
        self,
        user_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        *,
        wallet_id: uuid.UUID | None = None,
        currency: str | None = None,
        direction: str | None = None,
        status: TransactionStatus | None = None,
        category_id: uuid.UUID | None = None,
    ) -> list[WalletLedgerEntry]:
        entry_type = _ENTRY_TYPES_BY_DIRECTION.get(direction) if direction else None

        if is_supabase_session(self.db):
            wallets = self.db.fetch_many(Wallet, {"user_id": f"eq.{user_id}", "select": "id"})
            wallet_ids = [w.id for w in wallets if wallet_id is None or w.id == wallet_id]
            if not wallet_ids:
                return []
            joined = ",".join(str(w) for w in wallet_ids)
            entries = self.db.fetch_many(
                WalletLedgerEntry,
                {
                    "wallet_id": f"in.({joined})",
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
                if entry.entry_type not in (LedgerEntryType.DEBIT, LedgerEntryType.CREDIT):
                    continue
                if entry_type is not None and entry.entry_type != entry_type:
                    continue
                if currency is not None and entry.currency != currency:
                    continue
                transaction = by_id.get(entry.transaction_id)
                if transaction is None:
                    continue
                if status is not None and transaction.status != status:
                    continue
                if category_id is not None and transaction.category_id != category_id:
                    continue
                entry.transaction = transaction
                hydrated_entries.append(entry)
            return hydrated_entries

        user_wallet_ids = select(Wallet.id).where(Wallet.user_id == user_id)
        stmt = (
            select(WalletLedgerEntry)
            .join(Transaction, WalletLedgerEntry.transaction_id == Transaction.id)
            .where(
                WalletLedgerEntry.wallet_id.in_(user_wallet_ids),
                WalletLedgerEntry.created_at >= period_start,
                WalletLedgerEntry.created_at <= period_end,
                WalletLedgerEntry.entry_type.in_([LedgerEntryType.DEBIT, LedgerEntryType.CREDIT]),
            )
            .options(joinedload(WalletLedgerEntry.transaction))
            .order_by(WalletLedgerEntry.created_at)
        )
        if wallet_id is not None:
            stmt = stmt.where(WalletLedgerEntry.wallet_id == wallet_id)
        if currency is not None:
            stmt = stmt.where(WalletLedgerEntry.currency == currency)
        if entry_type is not None:
            stmt = stmt.where(WalletLedgerEntry.entry_type == entry_type)
        if status is not None:
            stmt = stmt.where(Transaction.status == status)
        if category_id is not None:
            stmt = stmt.where(Transaction.category_id == category_id)
        return list(self.db.scalars(stmt))

    def get_category_names(self, category_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not category_ids:
            return {}
        if is_supabase_session(self.db):
            joined = ",".join(str(category_id) for category_id in category_ids)
            categories = self.db.fetch_many(TransactionCategory, {"id": f"in.({joined})"})
            return {category.id: category.name for category in categories}
        stmt = select(TransactionCategory).where(TransactionCategory.id.in_(category_ids))
        return {category.id: category.name for category in self.db.scalars(stmt)}


class ExportJobRepository:
    """History of generated exports — see exports/models.py's ExportJob
    docstring for how this deviates from architecture.md's async-job shape."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, job: ExportJob) -> ExportJob:
        if is_supabase_session(self.db):
            return self.db.add(job)
        self.db.add(job)
        self.db.flush()
        return job

    def list_for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[ExportJob]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                ExportJob, {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": str(limit)}
            )
        stmt = (
            select(ExportJob).where(ExportJob.user_id == user_id).order_by(ExportJob.created_at.desc()).limit(limit)
        )
        return list(self.db.scalars(stmt))

    def get_owned_by_id(self, user_id: uuid.UUID, job_id: uuid.UUID) -> ExportJob | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(ExportJob, {"id": f"eq.{job_id}", "user_id": f"eq.{user_id}"})
        stmt = select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user_id)
        return self.db.scalar(stmt)
