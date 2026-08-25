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
    available signal. Both stay binary/fixed-point: device trust and
    location-seen-before are categorical facts, not magnitudes — there's no
    natural "how untrusted" or "how far from a known location" scale to
    proportion against with the data actually available.
  - HIGH_AMOUNT / HIGH_VELOCITY / REWARD_ABUSE_PATTERN: proportional. Each
    scales from a base point value at its minimum trigger condition up to a
    capped maximum as the signal gets further past that minimum (further
    over the user's average amount, more transactions in the window, more
    repeats to the same merchant) — see _scaled_points(). Computed from the
    user's own recent transaction history via the existing
    TransactionRepository.list_for_user (no changes to transactions/
    needed) — averages/window counts are all done in Python over Decimal
    amounts, never floats. HIGH_VELOCITY deliberately excludes whatever
    transactions REWARD_ABUSE_PATTERN already counted (see
    _velocity_and_abuse_flags) — a burst of near-identical repeats to one
    merchant is a single underlying behavior, not two independent signals,
    so it's scored once rather than double-counted under both flags.
  - UNUSUAL_TIME: fires when a payment lands inside a fixed UTC "night
    window" the user has no history of transacting in — see
    _unusual_time_flag() for the exact rule and its known limitation (no
    per-user timezone is stored anywhere, so this is UTC-relative, not
    local-time-relative).

Multiple co-occurring flags are combined with a small multiplier, not a
plain sum — see _combine_score() for the exact formula.

IMPOSSIBLE_TRAVEL (comparing locations across two transactions) was
considered and deliberately skipped: no per-transaction or per-merchant
location field exists anywhere in this schema, only UserDevice.mock_location
resolved via "most recently active session" — a current-state lookup, not a
historical one, so it can't answer "where was transaction N-1 relative to
transaction N".
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.analytics.schemas import SpendingByTypeResponse
from app.analytics.service import AnalyticsService
from app.auth.models import UserDevice
from app.cards.models import CardStatus, CardType
from app.cards.repository import CardRepository
from app.core.exceptions import ConflictError, NotFoundError
from app.fraud.models import FraudCase, FraudCaseStatus, FraudFlag, FraudFlagCode
from app.fraud.repository import FraudRepository
from app.fraud.schemas import FraudAgentAnalysisPublic, FraudCaseDetail, FraudCaseSummary, FraudFlagPublic, FraudRiskLevel
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.users.models import User
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository

# Recalibrated alongside the proportional-scoring/weighted-combination changes
# below (was a flat 50) — see the calibration table in the task report for
# the before/after scores this was picked against.
FRAUD_SCORE_THRESHOLD = Decimal("65")

# NEW_DEVICE / UNUSUAL_COUNTRY: binary/categorical, see module docstring.
NEW_DEVICE_POINTS = Decimal("25")
UNUSUAL_COUNTRY_POINTS = Decimal("20")

# HIGH_AMOUNT: proportional. BASE_POINTS at exactly HIGH_AMOUNT_MULTIPLIER (the
# minimum ratio-to-average needed to trigger at all), +POINTS_PER_EXTRA_MULTIPLE
# for each additional whole multiple of the user's average beyond that, capped
# at MAX_POINTS so one extreme outlier can't dominate the score by itself.
HIGH_AMOUNT_MULTIPLIER = Decimal("3")
HIGH_AMOUNT_MIN_HISTORY = 3
HIGH_AMOUNT_BASE_POINTS = Decimal("15")
HIGH_AMOUNT_POINTS_PER_EXTRA_MULTIPLE = Decimal("5")
HIGH_AMOUNT_MAX_POINTS = Decimal("40")

# HIGH_VELOCITY: proportional, same base/per-extra/cap pattern keyed on how
# many transactions beyond HIGH_VELOCITY_MIN_COUNT fell inside the window.
HIGH_VELOCITY_WINDOW = timedelta(minutes=5)
HIGH_VELOCITY_MIN_COUNT = 5
HIGH_VELOCITY_BASE_POINTS = Decimal("15")
HIGH_VELOCITY_POINTS_PER_EXTRA = Decimal("4")
HIGH_VELOCITY_MAX_POINTS = Decimal("35")

# REWARD_ABUSE_PATTERN: proportional, same pattern keyed on how many
# near-identical repeats beyond REWARD_ABUSE_MIN_COUNT fell inside the window.
REWARD_ABUSE_WINDOW = timedelta(minutes=10)
REWARD_ABUSE_MIN_COUNT = 3
REWARD_ABUSE_BASE_POINTS = Decimal("20")
REWARD_ABUSE_POINTS_PER_EXTRA = Decimal("6")
REWARD_ABUSE_MAX_POINTS = Decimal("40")

# UNUSUAL_TIME: binary — a payment inside this UTC window with no precedent of
# this user transacting in that same window before. Deliberately UTC-relative:
# nothing in the User model stores a per-user timezone, so a user whose local
# night genuinely falls outside 01:00-05:00 UTC won't be caught by this, and
# a user whose normal daytime happens to fall inside it will simply build up
# precedent on their first few transactions and stop triggering. No
# MIN_HISTORY gate like HIGH_AMOUNT has — this is a "have I ever seen this
# before" absence-check, not a statistical average, so it doesn't need one.
UNUSUAL_TIME_WINDOW_START_HOUR = 1  # 01:00 UTC
UNUSUAL_TIME_WINDOW_END_HOUR = 5  # up to but not including 05:00 UTC
UNUSUAL_TIME_POINTS = Decimal("10")

# Weighted combination: co-occurring flags are treated as reinforcing each
# other, not just independent additive evidence. +15% per flag beyond the
# first, capped at +40% (reached at 4 flags) so it can't spiral unboundedly
# as more flags stack — see _combine_score() for the exact formula.
MULTI_FLAG_BONUS_PER_EXTRA_FLAG = Decimal("0.15")
MULTI_FLAG_BONUS_MAX = Decimal("0.40")

FlagHit = tuple[FraudFlagCode, Decimal, str]


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) silently drops tzinfo on DateTime(timezone=True)
    columns on read-back, while Postgres (production) preserves it — normalize
    here so window comparisons below never mix naive and aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _scaled_points(over_minimum: Decimal, base: Decimal, per_extra: Decimal, max_points: Decimal) -> Decimal:
    """base + per_extra * over_minimum, capped at max_points. `over_minimum`
    must already be >= 0 — callers only invoke this once their own minimum-
    trigger condition is met, so the result is always at least `base`."""
    return min(base + per_extra * over_minimum, max_points)


def _combine_score(flags: list[FlagHit]) -> Decimal:
    """Weighted combination, not a plain sum: multiple co-occurring flags are
    treated as reinforcing each other, since several weak signals firing
    together is more suspicious than the same signals firing in isolation on
    unrelated transactions.

    combined = sum(points) * (1 + min(0.15 * (flag_count - 1), 0.40))

    So: 1 flag -> x1.00 (no change from a plain sum). 2 flags -> x1.15.
    3 flags -> x1.30. 4+ flags -> x1.40 (capped — a 5th, 6th, ... co-occurring
    flag no longer raises the multiplier, only the base sum does).
    """
    if not flags:
        return Decimal("0")
    base_sum = sum((points for _, points, _ in flags), Decimal("0"))
    bonus = min(MULTI_FLAG_BONUS_PER_EXTRA_FLAG * (len(flags) - 1), MULTI_FLAG_BONUS_MAX)
    combined = base_sum * (Decimal("1") + bonus)
    return combined.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class FraudDecision:
    blocked: bool
    score: Decimal
    case: FraudCase | None = None


@dataclass
class SpendingProfile:
    """Read-only "what's normal for this user" baseline. Not a scoring
    decision by itself — a lookup other code (evaluate_transaction today,
    AI agent tools later) can build on."""

    average_card_payment_amount: Decimal | None
    card_payment_history_count: int
    spending_by_type: SpendingByTypeResponse


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
        unusual_time = self._unusual_time_flag(transaction)
        if unusual_time is not None:
            flags.append(unusual_time)

        score = _combine_score(flags)
        transaction.fraud_score = score

        if not flags or score < FRAUD_SCORE_THRESHOLD:
            return FraudDecision(blocked=False, score=score, case=None)

        case = self._hold_and_create_case(transaction, wallet, score, flags)
        return FraudDecision(blocked=True, score=score, case=case)

    def get_recent_activity(
        self, user_id: uuid.UUID, window: timedelta = timedelta(hours=24), as_of: datetime | None = None
    ) -> list[Transaction]:
        """This user's transactions within `window` of `as_of` (defaults to
        now) — the same underlying lookup _velocity_and_abuse_flags() uses
        internally (with its own shorter windows), extracted as a standalone,
        independently-callable read.

        `as_of` lets a caller anchor to a specific point in time rather than
        wall-clock now — evaluate_transaction() uses this to anchor to the
        transaction being scored, so tests with fixed historical timestamps
        get reproducible results regardless of when the test actually runs.
        """
        reference = _as_aware_utc(as_of) if as_of is not None else datetime.now(timezone.utc)
        cutoff = reference - window
        return [t for t in self.transactions.list_for_user(user_id, limit=100) if _as_aware_utc(t.created_at) >= cutoff]

    def get_user_spending_profile(self, user_id: uuid.UUID) -> SpendingProfile:
        """Combines a card-payment average baseline with this month's
        category breakdown into one read-only "is this normal for this
        user" call, usable independently of evaluate_transaction().

        Deliberately not reused internally by _high_amount_flag(): that
        check only needs the average, and this method also computes a full
        AnalyticsService.spending_by_type() aggregate, which would add an
        unnecessary extra query to evaluate_transaction()'s hot path (it
        runs synchronously inside create_card_payment, blocking the
        payment). _high_amount_flag() keeps its own lightweight average
        computation instead.
        """
        history = [
            t
            for t in self.transactions.list_for_user(user_id, limit=100)
            if t.type == TransactionType.CARD_PAYMENT and t.status == TransactionStatus.COMPLETED
        ]
        average = (sum((t.amount for t in history), Decimal("0")) / len(history)) if history else None
        now = datetime.now(timezone.utc)
        spending = AnalyticsService(self.db).spending_by_type(user_id, now.year, now.month)
        return SpendingProfile(
            average_card_payment_amount=average,
            card_payment_history_count=len(history),
            spending_by_type=spending,
        )

    def get_known_devices(self, user_id: uuid.UUID) -> list[UserDevice]:
        """All devices ever seen for this user, most-recently-active first —
        a thin public wrapper over the repository lookups _device_flags()
        uses internally, extracted for investigation/tool use (the Fraud
        Investigation Agent) outside evaluate_transaction()."""
        devices = self.repository.list_devices_for_user(user_id)
        return sorted(devices, key=lambda device: device.last_seen_at, reverse=True)

    def save_agent_analysis(self, case: FraudCase, risk_level: FraudRiskLevel, explanation: str) -> FraudCase:
        """Persists the Fraud Investigation Agent's qualitative output onto
        FraudCase.agent_analysis (JSON-serialized). Advisory only — never
        touches risk_score or status. Called only from the admin-triggered
        POST /fraud/cases/{id}/investigate endpoint (ai/fraud/agent.py),
        never automatically."""
        payload = FraudAgentAnalysisPublic(
            risk_level=risk_level, explanation=explanation, generated_at=datetime.now(timezone.utc)
        )
        case.agent_analysis = payload.model_dump_json()
        self.db.flush()
        return case

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
        ratio = transaction.amount / average
        if ratio <= HIGH_AMOUNT_MULTIPLIER:
            return None

        points = _scaled_points(
            ratio - HIGH_AMOUNT_MULTIPLIER, HIGH_AMOUNT_BASE_POINTS, HIGH_AMOUNT_POINTS_PER_EXTRA_MULTIPLE, HIGH_AMOUNT_MAX_POINTS
        )
        return (
            FraudFlagCode.HIGH_AMOUNT,
            points,
            f"{transaction.amount} is {ratio.quantize(Decimal('0.1'))}x this user's average card payment "
            f"({average.quantize(Decimal('0.01'))})",
        )

    def _velocity_and_abuse_flags(self, transaction: Transaction) -> list[FlagHit]:
        flags: list[FlagHit] = []
        now = _as_aware_utc(transaction.created_at or datetime.now(timezone.utc))
        lookback = max(HIGH_VELOCITY_WINDOW, REWARD_ABUSE_WINDOW)
        recent = [
            t
            for t in self.get_recent_activity(transaction.initiator_user_id, window=lookback, as_of=now)
            if t.id != transaction.id
        ]

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
        total_velocity = velocity_count + 1
        if total_velocity >= HIGH_VELOCITY_MIN_COUNT:
            minutes = HIGH_VELOCITY_WINDOW.seconds // 60
            points = _scaled_points(
                Decimal(total_velocity - HIGH_VELOCITY_MIN_COUNT),
                HIGH_VELOCITY_BASE_POINTS,
                HIGH_VELOCITY_POINTS_PER_EXTRA,
                HIGH_VELOCITY_MAX_POINTS,
            )
            flags.append(
                (FraudFlagCode.HIGH_VELOCITY, points, f"{velocity_count} other transactions within {minutes} minutes")
            )

        total_matching = len(matching) + 1
        if total_matching >= REWARD_ABUSE_MIN_COUNT:
            minutes = REWARD_ABUSE_WINDOW.seconds // 60
            points = _scaled_points(
                Decimal(total_matching - REWARD_ABUSE_MIN_COUNT),
                REWARD_ABUSE_BASE_POINTS,
                REWARD_ABUSE_POINTS_PER_EXTRA,
                REWARD_ABUSE_MAX_POINTS,
            )
            flags.append(
                (
                    FraudFlagCode.REWARD_ABUSE_PATTERN,
                    points,
                    f"{total_matching} near-identical payments to the same merchant within {minutes} minutes",
                )
            )
        return flags

    def _unusual_time_flag(self, transaction: Transaction) -> FlagHit | None:
        now = _as_aware_utc(transaction.created_at or datetime.now(timezone.utc))
        hour = now.hour
        if not (UNUSUAL_TIME_WINDOW_START_HOUR <= hour < UNUSUAL_TIME_WINDOW_END_HOUR):
            return None

        history = [
            t
            for t in self.transactions.list_for_user(transaction.initiator_user_id, limit=100)
            if t.type == TransactionType.CARD_PAYMENT and t.status == TransactionStatus.COMPLETED and t.id != transaction.id
        ]
        has_night_precedent = any(
            UNUSUAL_TIME_WINDOW_START_HOUR <= _as_aware_utc(t.created_at).hour < UNUSUAL_TIME_WINDOW_END_HOUR
            for t in history
        )
        if has_night_precedent:
            return None

        return (
            FraudFlagCode.UNUSUAL_TIME,
            UNUSUAL_TIME_POINTS,
            f"Payment at {hour:02d}:00 UTC, a time this user has no prior completed card payments in "
            f"({UNUSUAL_TIME_WINDOW_START_HOUR:02d}:00-{UNUSUAL_TIME_WINDOW_END_HOUR:02d}:00 UTC)",
        )

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
        agent_analysis = (
            FraudAgentAnalysisPublic.model_validate_json(case.agent_analysis) if case.agent_analysis else None
        )
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
            agent_analysis=agent_analysis,
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
