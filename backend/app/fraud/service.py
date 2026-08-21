"""Deterministic fraud engine (architecture.md §32).

architecture.md §44 rule 3 applies here too: fraud scoring is computed in
code, never by an LLM — the (not yet built) Fraud Investigation Agent on
feature/dev4/ai-agents will only ever explain a score that's already been
computed here, never produce one itself.

Flag signals and their data sources:
  - NEW_DEVICE / UNUSUAL_COUNTRY: `create_card_payment` isn't passed any
    device/session context of its own, so "which device is paying" is
    inferred from the user's most recently active UserSession -> UserDevice
    (app.auth.models). UNUSUAL_COUNTRY uses UserDevice.mock_location as a
    proxy for transaction location — neither Transaction nor Merchant has a
    country field in this schema, so device location is the closest
    available signal.
  - HIGH_AMOUNT / HIGH_VELOCITY / REWARD_ABUSE_PATTERN: computed from the
    user's own recent transaction history via the existing
    TransactionRepository.list_for_user (no changes to transactions/
    needed) — averages/window counts are all done in Python over Decimal
    amounts, never floats. HIGH_VELOCITY deliberately excludes whatever
    transactions REWARD_ABUSE_PATTERN already counted (see
    _velocity_and_abuse_flags) — a burst of near-identical repeats to one
    merchant is a single underlying behavior, not two independent signals,
    so it's scored once rather than double-counted under both flags.

UNUSUAL_TIME is intentionally not implemented (dropped from scope).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.cards.models import CardStatus, CardType
from app.cards.repository import CardRepository
from app.core.exceptions import ConflictError, NotFoundError
from app.fraud.models import FraudCase, FraudCaseStatus, FraudFlag, FraudFlagCode
from app.fraud.repository import FraudRepository
from app.fraud.schemas import FraudCaseDetail, FraudCaseSummary, FraudFlagPublic
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.users.models import User
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository

FRAUD_SCORE_THRESHOLD = Decimal("50")

NEW_DEVICE_POINTS = Decimal("25")
HIGH_AMOUNT_POINTS = Decimal("30")
UNUSUAL_COUNTRY_POINTS = Decimal("20")
REWARD_ABUSE_PATTERN_POINTS = Decimal("35")
HIGH_VELOCITY_POINTS = Decimal("25")

HIGH_AMOUNT_MULTIPLIER = Decimal("3")
HIGH_AMOUNT_MIN_HISTORY = 3

HIGH_VELOCITY_WINDOW = timedelta(minutes=5)
HIGH_VELOCITY_MIN_COUNT = 5

REWARD_ABUSE_WINDOW = timedelta(minutes=10)
REWARD_ABUSE_MIN_COUNT = 3

FlagHit = tuple[FraudFlagCode, Decimal, str]


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) silently drops tzinfo on DateTime(timezone=True)
    columns on read-back, while Postgres (production) preserves it — normalize
    here so window comparisons below never mix naive and aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass
class FraudDecision:
    blocked: bool
    score: Decimal
    case: FraudCase | None = None


class FraudService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = FraudRepository(db)
        self.transactions = TransactionRepository(db)
        self.wallets = WalletRepository(db)
        self.cards = CardRepository(db)

    def evaluate_transaction(self, transaction: Transaction, wallet: Wallet) -> FraudDecision:
        flags: list[FlagHit] = []
        flags.extend(self._device_flags(transaction.initiator_user_id))
        high_amount = self._high_amount_flag(transaction)
        if high_amount is not None:
            flags.append(high_amount)
        flags.extend(self._velocity_and_abuse_flags(transaction))

        score = sum((points for _, points, _ in flags), Decimal("0"))
        transaction.fraud_score = score

        if not flags or score < FRAUD_SCORE_THRESHOLD:
            return FraudDecision(blocked=False, score=score, case=None)

        case = self._hold_and_create_case(transaction, wallet, score, flags)
        return FraudDecision(blocked=True, score=score, case=case)

    def _device_flags(self, user_id: uuid.UUID) -> list[FlagHit]:
        flags: list[FlagHit] = []
        device = self.repository.get_latest_device_for_user(user_id)
        if device is None:
            return flags

        if not device.trusted:
            label = device.device_name or device.device_type or "unknown device"
            flags.append((FraudFlagCode.NEW_DEVICE, NEW_DEVICE_POINTS, f"Payment from an untrusted device ({label})"))

        if device.mock_location:
            other_locations = {
                other.mock_location
                for other in self.repository.list_devices_for_user(user_id)
                if other.id != device.id and other.mock_location
            }
            if other_locations and device.mock_location not in other_locations:
                flags.append(
                    (
                        FraudFlagCode.UNUSUAL_COUNTRY,
                        UNUSUAL_COUNTRY_POINTS,
                        f"Payment from {device.mock_location}, not previously seen for this user",
                    )
                )
        return flags

    def _high_amount_flag(self, transaction: Transaction) -> FlagHit | None:
        history = [
            t
            for t in self.transactions.list_for_user(transaction.initiator_user_id, limit=100)
            if t.type == TransactionType.CARD_PAYMENT and t.status == TransactionStatus.COMPLETED
        ]
        if len(history) < HIGH_AMOUNT_MIN_HISTORY:
            return None

        average = sum((t.amount for t in history), Decimal("0")) / len(history)
        if transaction.amount <= average * HIGH_AMOUNT_MULTIPLIER:
            return None
        return (
            FraudFlagCode.HIGH_AMOUNT,
            HIGH_AMOUNT_POINTS,
            f"{transaction.amount} is more than {HIGH_AMOUNT_MULTIPLIER}x this user's average "
            f"card payment ({average.quantize(Decimal('0.01'))})",
        )

    def _velocity_and_abuse_flags(self, transaction: Transaction) -> list[FlagHit]:
        flags: list[FlagHit] = []
        now = _as_aware_utc(transaction.created_at or datetime.now(timezone.utc))
        recent = [
            t
            for t in self.transactions.list_for_user(transaction.initiator_user_id, limit=100)
            if t.id != transaction.id
        ]

        # Computed first and excluded from HIGH_VELOCITY below: a burst of
        # near-identical repeats to the same merchant is one underlying
        # behavior, not two independent pieces of evidence — without this,
        # every REWARD_ABUSE_PATTERN case also double-counted as HIGH_VELOCITY
        # off the exact same transactions.
        matching = [
            t
            for t in recent
            if transaction.merchant_id is not None
            and t.type == TransactionType.CARD_PAYMENT
            and t.merchant_id == transaction.merchant_id
            and _as_aware_utc(t.created_at) >= now - REWARD_ABUSE_WINDOW
            and abs(t.amount - transaction.amount) < Decimal("0.01")
        ]
        matching_ids = {t.id for t in matching}

        velocity_count = sum(
            1
            for t in recent
            if t.id not in matching_ids and _as_aware_utc(t.created_at) >= now - HIGH_VELOCITY_WINDOW
        )
        if velocity_count + 1 >= HIGH_VELOCITY_MIN_COUNT:
            minutes = HIGH_VELOCITY_WINDOW.seconds // 60
            flags.append(
                (
                    FraudFlagCode.HIGH_VELOCITY,
                    HIGH_VELOCITY_POINTS,
                    f"{velocity_count} other transactions within {minutes} minutes",
                )
            )

        if len(matching) + 1 >= REWARD_ABUSE_MIN_COUNT:
            minutes = REWARD_ABUSE_WINDOW.seconds // 60
            flags.append(
                (
                    FraudFlagCode.REWARD_ABUSE_PATTERN,
                    REWARD_ABUSE_PATTERN_POINTS,
                    f"{len(matching) + 1} near-identical payments to the same merchant within {minutes} minutes",
                )
            )
        return flags

    def _hold_and_create_case(
        self, transaction: Transaction, wallet: Wallet, score: Decimal, flags: list[FlagHit]
    ) -> FraudCase:
        wallet.available_balance -= transaction.amount
        wallet.reserved_balance += transaction.amount
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.HOLD,
                amount=transaction.amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )
        transaction.status = TransactionStatus.PENDING_REVIEW

        case = self.repository.add(
            FraudCase(
                transaction_id=transaction.id,
                user_id=transaction.initiator_user_id,
                risk_score=score,
                hold_amount=transaction.amount,
            )
        )
        for code, points, description in flags:
            self.repository.add_flag(FraudFlag(fraud_case_id=case.id, code=code, points=points, description=description))
        self.db.flush()
        return case

    def approve(self, case: FraudCase, admin: User) -> FraudCase:
        if case.status != FraudCaseStatus.PENDING_REVIEW:
            raise ConflictError("Fraud case has already been decided")

        transaction = self.transactions.get_by_id(case.transaction_id)
        wallet = self.wallets.get_by_id(transaction.source_wallet_id)

        wallet.reserved_balance -= case.hold_amount
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=case.hold_amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)

        if transaction.card_id is not None:
            card = self.cards.get_by_id(transaction.card_id)
            if card is not None and card.type == CardType.ONE_TIME:
                card.one_time_remaining = max(0, (card.one_time_remaining or 1) - 1)
                if card.one_time_remaining == 0:
                    card.status = CardStatus.CANCELLED

        case.status = FraudCaseStatus.APPROVED
        case.decided_by_admin_id = admin.id
        case.decided_at = datetime.now(timezone.utc)
        self.db.flush()
        return case

    def reject(self, case: FraudCase, admin: User) -> FraudCase:
        if case.status != FraudCaseStatus.PENDING_REVIEW:
            raise ConflictError("Fraud case has already been decided")

        transaction = self.transactions.get_by_id(case.transaction_id)
        wallet = self.wallets.get_by_id(transaction.source_wallet_id)

        wallet.reserved_balance -= case.hold_amount
        wallet.available_balance += case.hold_amount
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.RELEASE,
                amount=case.hold_amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )
        transaction.status = TransactionStatus.REJECTED

        case.status = FraudCaseStatus.REJECTED
        case.decided_by_admin_id = admin.id
        case.decided_at = datetime.now(timezone.utc)
        self.db.flush()
        return case

    def get_case(self, case_id: uuid.UUID) -> FraudCase:
        case = self.repository.get_by_id(case_id)
        if case is None:
            raise NotFoundError("Fraud case not found")
        return case

    def list_pending(self) -> list[FraudCaseSummary]:
        return [self._to_summary(case) for case in self.repository.list_pending()]

    def to_detail(self, case: FraudCase) -> FraudCaseDetail:
        transaction = self.transactions.get_by_id(case.transaction_id)
        flags = self.repository.list_flags_for_case(case.id)
        return FraudCaseDetail(
            id=case.id,
            transaction_id=case.transaction_id,
            user_id=case.user_id,
            risk_score=case.risk_score,
            status=case.status,
            hold_amount=case.hold_amount,
            created_at=case.created_at,
            flag_codes=[flag.code for flag in flags],
            decided_by_admin_id=case.decided_by_admin_id,
            decided_at=case.decided_at,
            flags=[FraudFlagPublic(id=f.id, code=f.code, points=f.points, description=f.description) for f in flags],
            transaction_amount=transaction.amount,
            transaction_currency=transaction.currency,
            transaction_description=transaction.description,
            transaction_created_at=transaction.created_at,
        )

    def _to_summary(self, case: FraudCase) -> FraudCaseSummary:
        flags = self.repository.list_flags_for_case(case.id)
        return FraudCaseSummary(
            id=case.id,
            transaction_id=case.transaction_id,
            user_id=case.user_id,
            risk_score=case.risk_score,
            status=case.status,
            hold_amount=case.hold_amount,
            created_at=case.created_at,
            flag_codes=[flag.code for flag in flags],
        )
