"""Data-access layer for analytics — read-only aggregate queries over Transaction
and WalletLedgerEntry."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, WalletLedgerEntry


class AnalyticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def spending_by_type(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[tuple]:
        stmt = (
            select(
                Transaction.type,
                Transaction.currency,
                func.sum(Transaction.amount),
                func.count(Transaction.id),
            )
            .where(
                Transaction.initiator_user_id == user_id,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.created_at >= period_start,
                Transaction.created_at < period_end,
            )
            .group_by(Transaction.type, Transaction.currency)
        )
        return list(self.db.execute(stmt).all())

    def completed_transactions_in_range(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[tuple]:
        stmt = select(Transaction.amount, Transaction.currency, Transaction.created_at).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= period_start,
            Transaction.created_at <= period_end,
        )
        return list(self.db.execute(stmt).all())

    def net_ledger_change(self, wallet_id: uuid.UUID, period_start: datetime, period_end: datetime) -> Decimal:
        """Net movement (CREDIT - DEBIT) on a wallet's ledger within a period.

        Deliberately ignores HOLD/RELEASE entries — those represent funds
        pending fraud review, not confirmed income/spend, so they'd distort a
        spending-trend projection.
        """
        stmt = (
            select(WalletLedgerEntry.entry_type, func.sum(WalletLedgerEntry.amount))
            .where(
                WalletLedgerEntry.wallet_id == wallet_id,
                WalletLedgerEntry.created_at >= period_start,
                WalletLedgerEntry.created_at <= period_end,
                WalletLedgerEntry.entry_type.in_([LedgerEntryType.DEBIT, LedgerEntryType.CREDIT]),
            )
            .group_by(WalletLedgerEntry.entry_type)
        )
        totals = dict(self.db.execute(stmt).all())
        credit = totals.get(LedgerEntryType.CREDIT, Decimal("0"))
        debit = totals.get(LedgerEntryType.DEBIT, Decimal("0"))
        return credit - debit
