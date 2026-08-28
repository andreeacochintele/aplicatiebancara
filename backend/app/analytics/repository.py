"""Data-access layer for analytics — read-only aggregate queries over Transaction
and WalletLedgerEntry."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, not_, select
from sqlalchemy.orm import Session

from app.merchants.models import Merchant
from app.supabase import is_supabase_session
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.wallets.models import Wallet

_UNCATEGORIZED = "Other"


class AnalyticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _own_wallet_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """Wallet IDs owned by this user — used to tell an internal wallet-to-wallet
        transfer (not real spend) apart from an external transfer/IBAN payment
        (real spend) that both use TransactionType.TRANSFER."""
        if is_supabase_session(self.db):
            wallets = self.db.fetch_many(Wallet, {"user_id": f"eq.{user_id}"})
            return {wallet.id for wallet in wallets}
        return set(self.db.scalars(select(Wallet.id).where(Wallet.user_id == user_id)))

    def _is_real_spend(self, transaction: Transaction, own_wallet_ids: set[uuid.UUID]) -> bool:
        """CASHBACK and SAVINGS_WITHDRAWAL are incoming money, not spend. A
        TRANSFER only counts as spend when it actually leaves the user — i.e.
        not a same-user wallet-to-wallet move (see architecture.md §26 / the
        analytics redesign brief). SAVINGS_CONTRIBUTION is real money leaving
        the wallet, so it counts same as any other outflow."""
        if transaction.type in (TransactionType.CASHBACK, TransactionType.SAVINGS_WITHDRAWAL):
            return False
        if transaction.type == TransactionType.TRANSFER and transaction.destination_wallet_id in own_wallet_ids:
            return False
        return True

    def spending_by_type(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[tuple]:
        own_wallet_ids = self._own_wallet_ids(user_id)

        if is_supabase_session(self.db):
            transactions = self.db.fetch_many(
                Transaction,
                {
                    "initiator_user_id": f"eq.{user_id}",
                    "status": f"eq.{TransactionStatus.COMPLETED.value}",
                    "and": f"(created_at.gte.{period_start.isoformat()},created_at.lt.{period_end.isoformat()})",
                },
            )
            totals: dict[tuple[object, str], dict[str, object]] = {}
            for transaction in transactions:
                if not self._is_real_spend(transaction, own_wallet_ids):
                    continue
                key = (transaction.type, transaction.currency)
                bucket = totals.setdefault(key, {"total": Decimal("0"), "count": 0})
                bucket["total"] += transaction.amount
                bucket["count"] += 1
            return [(tx_type, currency, item["total"], item["count"]) for (tx_type, currency), item in totals.items()]

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
                Transaction.type != TransactionType.CASHBACK,
                not_(
                    and_(
                        Transaction.type == TransactionType.TRANSFER,
                        Transaction.destination_wallet_id.isnot(None),
                        Transaction.destination_wallet_id.in_(own_wallet_ids),
                    )
                ),
            )
            .group_by(Transaction.type, Transaction.currency)
        )
        return list(self.db.execute(stmt).all())

    def spending_by_merchant_category(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[tuple]:
        """Card payments only, grouped by the paying merchant's own category
        — transfers and loan payments are never "spending at a merchant" and
        are excluded outright rather than filtered via _is_real_spend, which
        only knows how to tell real spend apart within a much broader set of
        transaction types than this view needs."""
        if is_supabase_session(self.db):
            transactions = self.db.fetch_many(
                Transaction,
                {
                    "initiator_user_id": f"eq.{user_id}",
                    "status": f"eq.{TransactionStatus.COMPLETED.value}",
                    "type": f"eq.{TransactionType.CARD_PAYMENT.value}",
                    "and": f"(created_at.gte.{period_start.isoformat()},created_at.lt.{period_end.isoformat()})",
                },
            )
            merchants_by_id = {m.id: m for m in self.db.fetch_many(Merchant, {})}
            totals: dict[tuple[str, str], dict[str, object]] = {}
            for transaction in transactions:
                merchant = merchants_by_id.get(transaction.merchant_id) if transaction.merchant_id else None
                category = merchant.category if merchant is not None else _UNCATEGORIZED
                key = (category, transaction.currency)
                bucket = totals.setdefault(key, {"total": Decimal("0"), "count": 0})
                bucket["total"] += transaction.amount
                bucket["count"] += 1
            return [(category, currency, item["total"], item["count"]) for (category, currency), item in totals.items()]

        category_col = func.coalesce(Merchant.category, _UNCATEGORIZED)
        stmt = (
            select(
                category_col,
                Transaction.currency,
                func.sum(Transaction.amount),
                func.count(Transaction.id),
            )
            .select_from(Transaction)
            .outerjoin(Merchant, Merchant.id == Transaction.merchant_id)
            .where(
                Transaction.initiator_user_id == user_id,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.type == TransactionType.CARD_PAYMENT,
                Transaction.created_at >= period_start,
                Transaction.created_at < period_end,
            )
            .group_by(category_col, Transaction.currency)
        )
        return list(self.db.execute(stmt).all())

    def spend_transactions_for_counterparties(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[Transaction]:
        """Real-spend transactions (see _is_real_spend) with merchant_id/
        counterparty_user_id/description intact, for top_counterparties() to
        resolve a display name from — unlike spending_by_merchant_category,
        this isn't card-payments-only, so an IBAN/phone transfer to an
        external vendor counts too."""
        own_wallet_ids = self._own_wallet_ids(user_id)

        if is_supabase_session(self.db):
            transactions = self.db.fetch_many(
                Transaction,
                {
                    "initiator_user_id": f"eq.{user_id}",
                    "status": f"eq.{TransactionStatus.COMPLETED.value}",
                    "and": f"(created_at.gte.{period_start.isoformat()},created_at.lt.{period_end.isoformat()})",
                },
            )
            return [t for t in transactions if self._is_real_spend(t, own_wallet_ids)]

        stmt = select(Transaction).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= period_start,
            Transaction.created_at < period_end,
        )
        return [t for t in self.db.scalars(stmt) if self._is_real_spend(t, own_wallet_ids)]

    def completed_transactions_in_range(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[tuple]:
        own_wallet_ids = self._own_wallet_ids(user_id)

        if is_supabase_session(self.db):
            transactions = self.db.fetch_many(
                Transaction,
                {
                    "initiator_user_id": f"eq.{user_id}",
                    "status": f"eq.{TransactionStatus.COMPLETED.value}",
                    "created_at": f"gte.{period_start.isoformat()}",
                    "created_at": f"lte.{period_end.isoformat()}",
                    "order": "created_at.asc",
                },
            )
            return [
                (transaction.amount, transaction.currency, transaction.created_at)
                for transaction in transactions
                if self._is_real_spend(transaction, own_wallet_ids)
            ]

        stmt = select(Transaction.amount, Transaction.currency, Transaction.created_at).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= period_start,
            Transaction.created_at <= period_end,
            Transaction.type != TransactionType.CASHBACK,
            ~(
                (Transaction.type == TransactionType.TRANSFER)
                & Transaction.destination_wallet_id.in_(own_wallet_ids)
            ),
        )
        return list(self.db.execute(stmt).all())

    def net_ledger_change(self, wallet_id: uuid.UUID, period_start: datetime, period_end: datetime) -> Decimal:
        """Net movement (CREDIT - DEBIT) on a wallet's ledger within a period.

        Deliberately ignores HOLD/RELEASE entries — those represent funds
        pending fraud review, not confirmed income/spend, so they'd distort a
        spending-trend projection.
        """
        if is_supabase_session(self.db):
            entries = self.db.fetch_many(
                WalletLedgerEntry,
                {
                    "wallet_id": f"eq.{wallet_id}",
                    "created_at": f"gte.{period_start.isoformat()}",
                    "created_at": f"lte.{period_end.isoformat()}",
                    "entry_type": f"in.({LedgerEntryType.DEBIT.value},{LedgerEntryType.CREDIT.value})",
                },
            )
            credit = sum((entry.amount for entry in entries if entry.entry_type == LedgerEntryType.CREDIT), Decimal("0"))
            debit = sum((entry.amount for entry in entries if entry.entry_type == LedgerEntryType.DEBIT), Decimal("0"))
            return credit - debit

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

    def ledger_entries_since(self, wallet_id: uuid.UUID, period_start: datetime) -> list[tuple]:
        """DEBIT/CREDIT ledger entries for a wallet from period_start onward, oldest
        first, each carrying the resulting balance_after — used to reconstruct the
        wallet's balance at any earlier point without a dedicated history table.
        Ignores HOLD/RELEASE for the same reason net_ledger_change does.
        """
        if is_supabase_session(self.db):
            entries = self.db.fetch_many(
                WalletLedgerEntry,
                {
                    "wallet_id": f"eq.{wallet_id}",
                    "created_at": f"gte.{period_start.isoformat()}",
                    "entry_type": f"in.({LedgerEntryType.DEBIT.value},{LedgerEntryType.CREDIT.value})",
                    "order": "created_at.asc",
                },
            )
            return [(entry.entry_type, entry.amount, entry.balance_after, entry.created_at) for entry in entries]

        stmt = (
            select(
                WalletLedgerEntry.entry_type,
                WalletLedgerEntry.amount,
                WalletLedgerEntry.balance_after,
                WalletLedgerEntry.created_at,
            )
            .where(
                WalletLedgerEntry.wallet_id == wallet_id,
                WalletLedgerEntry.created_at >= period_start,
                WalletLedgerEntry.entry_type.in_([LedgerEntryType.DEBIT, LedgerEntryType.CREDIT]),
            )
            .order_by(WalletLedgerEntry.created_at.asc())
        )
        return list(self.db.execute(stmt).all())
