"""Deterministic fraud engine (architecture.md §32).

architecture.md §44 rule 3 applies here too: fraud scoring is computed in
code, never by an LLM — the (not yet built) Fraud Investigation Agent on
feature/dev4/ai-agents will only ever explain a score that's already been
computed here, never produce one itself.

What gets screened (SCREENED_TRANSACTION_TYPES): CARD_PAYMENT and TRANSFER
only. Everything else the ledger produces is either system-generated
(CASHBACK), gated by its own module's rules (LOAN_PAYMENT, SAVINGS_*), or
not a user-initiated outflow at all — a loan disbursement is a TRANSFER
with no source wallet and never reaches this service. Screening happens at
each engine seam before any balance moves: TransactionService's
create_card_payment / _execute_same_currency_transfer / _execute_fx_transfer,
and PaymentsService.create_iban_transfer's external leg. Bill-split and
payment-request settlements deliberately opt out (see
create_internal_transfer's `screen_for_fraud`).

Because a TRANSFER has a second leg a HOLD never touches, approve() credits
the destination wallet as well — see _credit_destination_if_transfer().
Amounts used for scoring and for the hold are always the SOURCE side, so a
cross-currency transfer is measured by what actually left the payer's
wallet; see _screened_amount().

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
  - REPEATED_TRANSFER_PATTERN: the transfer-side counterpart of
    REWARD_ABUSE_PATTERN, sharing its calibration and scaling. Both detect
    "N near-identical repeats to the same counterparty inside a short
    window"; they differ only in what counts as the counterparty
    (merchant_id vs destination_wallet_id — see _repeat_key()) and in the
    behavior they point at, which is why they're separate codes rather than
    one. Neither can fire without a counterparty id: an external IBAN
    transfer stores its IBAN only in free-text description, so repeats to
    one external account are not detectable here and rely on HIGH_VELOCITY.
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
    HIGH_AMOUNT's baseline and REWARD_ABUSE_PATTERN's near-identical-amount
    matching are both computed PER CURRENCY (a transaction is only ever
    compared against the user's own history in that same currency) — a
    wallet holder with, say, both RON and USD activity must never have a
    high-value RON payment scored against a blended RON+USD average, and
    must never have a RON payment counted as a "near-identical" repeat of a
    same-amount USD one. A user's first-ever payment in a given currency has
    no same-currency baseline to compare against: HIGH_AMOUNT simply doesn't
    fire for that payment (same as the existing insufficient-history
    fallback below) rather than falling back to a cross-currency average.
    HIGH_AMOUNT, HIGH_VELOCITY, and REWARD_ABUSE_PATTERN additionally allow
    a single, sufficiently extreme occurrence to cross FRAUD_SCORE_THRESHOLD
    on its own — see the raised MAX_POINTS on each below.
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
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.schemas import SpendingByTypeResponse
from app.analytics.service import AnalyticsService
from app.auth.models import UserDevice
from app.cards.models import Card, CardFreezeReason, CardStatus, CardType
from app.cards.repository import CardRepository
from app.cards.service import CardService
from app.core.exceptions import ConflictError, NotFoundError
from app.fraud.models import FraudCase, FraudCaseStatus, FraudFlag, FraudFlagCode
from app.fraud.repository import FraudRepository
from app.fraud.schemas import (
    FraudAgentAnalysisPublic,
    FraudCaseDetail,
    FraudCaseSummary,
    FraudFlagPublic,
    FraudRiskLevel,
    FrozenCardPublic,
)
from app.merchants.repository import MerchantRepository
from app.merchants.service import MerchantService
from app.notifications.service import NotificationsService
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.users.models import User
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository

# Recalibrated alongside the proportional-scoring/weighted-combination changes
# below (was a flat 50) — see the calibration table in the task report for
# the before/after scores this was picked against.
FRAUD_SCORE_THRESHOLD = Decimal("65")

# Only these two types are ever scored. Everything else the ledger produces
# is either system-generated (CASHBACK), already gated by its own module's
# rules (LOAN_PAYMENT, SAVINGS_*), or not a user-initiated outflow at all
# (a loan disbursement is a TRANSFER with no source wallet — it never
# reaches evaluate_transaction because nothing calls it there).
SCREENED_TRANSACTION_TYPES = frozenset({TransactionType.CARD_PAYMENT, TransactionType.TRANSFER})

# NEW_DEVICE / UNUSUAL_COUNTRY: binary/categorical, see module docstring.
NEW_DEVICE_POINTS = Decimal("25")
UNUSUAL_COUNTRY_POINTS = Decimal("20")

# HIGH_AMOUNT: proportional. BASE_POINTS at exactly HIGH_AMOUNT_MULTIPLIER (the
# minimum ratio-to-average needed to trigger at all), +POINTS_PER_EXTRA_MULTIPLE
# for each additional whole multiple of the user's average beyond that, capped
# at MAX_POINTS. The cap is deliberately set above FRAUD_SCORE_THRESHOLD (65):
# a merely-borderline payment (a couple of multiples over average) still scores
# close to BASE_POINTS as before, but a genuinely extreme outlier (e.g. ~10x
# the user's own average, i.e. HIGH_AMOUNT_MULTIPLIER + 7) can reach the cap
# and cross the threshold entirely on its own, without needing a second
# co-occurring flag — see the calibration table in the task report.
HIGH_AMOUNT_MULTIPLIER = Decimal("3")
HIGH_AMOUNT_MIN_HISTORY = 3
HIGH_AMOUNT_BASE_POINTS = Decimal("15")
HIGH_AMOUNT_POINTS_PER_EXTRA_MULTIPLE = Decimal("8")
HIGH_AMOUNT_MAX_POINTS = Decimal("70")

# HIGH_VELOCITY: proportional, same base/per-extra/cap pattern keyed on how
# many transactions beyond HIGH_VELOCITY_MIN_COUNT fell inside the window.
# Recalibrated tighter alongside REWARD_ABUSE_PATTERN above, for the same
# reason: 14 transactions in 5 minutes to cross the threshold on this flag
# alone (the original 15 base / +6 per extra) was too permissive. 30 base /
# +12 per extra crosses the threshold alone at the 8th transaction in the
# window (30, 42, 54, 66 for transactions 5, 6, 7, 8) - 3 over the minimum
# trigger count, same margin as REWARD_ABUSE_PATTERN's now uses relative to
# its own minimum.
HIGH_VELOCITY_WINDOW = timedelta(minutes=5)
HIGH_VELOCITY_MIN_COUNT = 5
HIGH_VELOCITY_BASE_POINTS = Decimal("30")
HIGH_VELOCITY_POINTS_PER_EXTRA = Decimal("12")
HIGH_VELOCITY_MAX_POINTS = Decimal("70")

# REWARD_ABUSE_PATTERN: proportional, same pattern keyed on how many
# near-identical repeats beyond REWARD_ABUSE_MIN_COUNT fell inside the
# window. Recalibrated tighter than HIGH_AMOUNT/HIGH_VELOCITY above: 11
# identical repeats to cross the threshold on this flag alone (the original
# 20 base / +6 per extra) proved far too permissive in practice — an
# obvious same-merchant, same-amount repeat-payment burst should hold well
# before a dozen repeats. 35 base / +10 per extra crosses the threshold
# alone at the 6th near-identical repeat (35, 45, 55, 65 for repeats
# 3, 4, 5, 6), while the bare-minimum 3-repeat case still just flags at
# BASE_POINTS rather than holding outright.
REWARD_ABUSE_WINDOW = timedelta(minutes=10)
REWARD_ABUSE_MIN_COUNT = 3
REWARD_ABUSE_BASE_POINTS = Decimal("35")
REWARD_ABUSE_POINTS_PER_EXTRA = Decimal("10")
REWARD_ABUSE_MAX_POINTS = Decimal("70")

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

# Fixed, hardcoded reminder attached to FraudCaseDetail (fraud/schemas.py)
# whenever a card is frozen with CardFreezeReason.FRAUD_HOLD for this case —
# see to_detail() below. Deliberately NOT part of the Fraud Investigation
# Agent's prompt/output (ai/fraud/agent.py): this text must read identically
# on every case regardless of what the LLM says, so it's a plain Python
# constant the service attaches itself, never model-generated content.
CARD_ACTIVATION_SAFETY_NOTICE = (
    "You may only activate this card if you've verified the customer's identity and confirmed "
    "their data is safe, after fully reviewing the report. The final decision is yours."
)

logger = logging.getLogger(__name__)

FlagHit = tuple[FraudFlagCode, Decimal, str]


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) silently drops tzinfo on DateTime(timezone=True)
    columns on read-back, while Postgres (production) preserves it — normalize
    here so window comparisons below never mix naive and aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _screened_amount(transaction: Transaction) -> Decimal:
    """What actually leaves the payer's wallet, in that wallet's currency.

    For a card payment and a same-currency transfer this is just `amount`.
    For a cross-currency transfer `amount`/`currency` describe the *target*
    side (what the recipient gets), while `source_amount`/`source_currency`
    describe what was debited — and it's the debited side that every fraud
    signal here cares about: "how big is this for this user", "is this the
    same amount as the last three", and how much gets put on HOLD. Comparing
    a 20 EUR target against a RON baseline would be meaningless.
    """
    return transaction.source_amount if transaction.source_amount is not None else transaction.amount


def _screened_currency(transaction: Transaction) -> str:
    """The currency `_screened_amount()` is denominated in — see above."""
    return transaction.source_currency if transaction.source_currency is not None else transaction.currency


def _type_label(transaction: Transaction) -> str:
    """Human wording for flag descriptions and analyst-facing data gaps."""
    return "card payment" if transaction.type == TransactionType.CARD_PAYMENT else "transfer"


def _repeat_key(transaction: Transaction) -> tuple[str, uuid.UUID] | None:
    """What "the same counterparty" means for repeat detection, per type: a
    card payment repeats against a merchant, a transfer against the
    destination wallet.

    None means repeats aren't detectable for this transaction at all — a
    merchant-less card payment, or a transfer leaving the bank (an external
    IBAN transfer has destination_wallet_id NULL, and the IBAN itself is
    only ever stored inside the free-text description, so there's no field
    to key on). Those bursts can still be caught by HIGH_VELOCITY, which
    doesn't need a counterparty; see this module's docstring.
    """
    if transaction.type == TransactionType.CARD_PAYMENT:
        return ("merchant", transaction.merchant_id) if transaction.merchant_id is not None else None
    if transaction.type == TransactionType.TRANSFER:
        return ("wallet", transaction.destination_wallet_id) if transaction.destination_wallet_id is not None else None
    return None


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
class CurrencySpendingProfile:
    """This user's card-payment baseline within a single currency — never
    blend this across currencies, see module docstring."""

    currency: str
    average_card_payment_amount: Decimal
    card_payment_history_count: int


@dataclass
class SpendingProfile:
    """Read-only "what's normal for this user" baseline. Not a scoring
    decision by itself — a lookup other code (evaluate_transaction today,
    AI agent tools later) can build on.

    `by_currency` is keyed by currency code — averaging across currencies
    would produce a meaningless blended figure (see module docstring), so
    there is deliberately no single blended "average amount" field here.
    `card_payment_history_count` is a plain count (not an average), so
    summing it across currencies is safe and stays as a total.
    """

    by_currency: dict[str, CurrencySpendingProfile]
    card_payment_history_count: int
    spending_by_type: SpendingByTypeResponse


class FraudService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = FraudRepository(db)
        self.transactions = TransactionRepository(db)
        self.wallets = WalletRepository(db)
        self.cards = CardRepository(db)
        self.merchants = MerchantRepository(db)

    def evaluate_transaction(
        self,
        transaction: Transaction,
        wallet: Wallet,
        *,
        batch_reference: str | None = None,
        batch_sibling_ids: frozenset[uuid.UUID] | None = None,
    ) -> FraudDecision:
        if transaction.type not in SCREENED_TRANSACTION_TYPES:
            # Deliberately leaves fraud_score NULL rather than writing 0:
            # "never screened" and "screened and came back clean" are
            # different facts, and an admin reading the column should be
            # able to tell them apart.
            return FraudDecision(blocked=False, score=Decimal("0"), case=None)

        # Fetched once and shared by every flag below. Each of these used to
        # run its own list_for_user() — the same query, three times over —
        # which on the Supabase REST backend is two HTTP round-trips apiece
        # (wallets, then transactions). Six round-trips became two, and this
        # runs synchronously inside the payment/transfer request, so it is
        # latency the user waits on. See app/supabase.py.
        history = self.transactions.list_for_user(transaction.initiator_user_id, limit=100)

        flags: list[FlagHit] = []
        flags.extend(self._device_flags(transaction.initiator_user_id))
        high_amount = self._high_amount_flag(transaction, history)
        if high_amount is not None:
            flags.append(high_amount)
        flags.extend(self._velocity_and_repeat_flags(transaction, history, batch_sibling_ids=batch_sibling_ids))
        unusual_time = self._unusual_time_flag(transaction, history)
        if unusual_time is not None:
            flags.append(unusual_time)

        score = _combine_score(flags)
        transaction.fraud_score = score

        if not flags or score < FRAUD_SCORE_THRESHOLD:
            return FraudDecision(blocked=False, score=score, case=None)

        case = self._hold_and_create_case(transaction, wallet, score, flags, batch_reference=batch_reference)
        return FraudDecision(blocked=True, score=score, case=case)

    def get_recent_activity(
        self,
        user_id: uuid.UUID,
        window: timedelta = timedelta(hours=24),
        as_of: datetime | None = None,
        history: list[Transaction] | None = None,
    ) -> list[Transaction]:
        """This user's transactions within `window` of `as_of` (defaults to
        now) — the same underlying lookup _velocity_and_abuse_flags() uses
        internally (with its own shorter windows), extracted as a standalone,
        independently-callable read.

        `as_of` lets a caller anchor to a specific point in time rather than
        wall-clock now — evaluate_transaction() uses this to anchor to the
        transaction being scored, so tests with fixed historical timestamps
        get reproducible results regardless of when the test actually runs.

        `history` lets a caller that has already fetched this user's
        transactions pass them in instead of paying for the same query again;
        evaluate_transaction() shares one fetch across all its flags this
        way. Left None, this fetches for itself as before.
        """
        reference = _as_aware_utc(as_of) if as_of is not None else datetime.now(timezone.utc)
        cutoff = reference - window
        if history is None:
            history = self.transactions.list_for_user(user_id, limit=100)
        return [t for t in history if _as_aware_utc(t.created_at) >= cutoff]

    def get_user_spending_profile(self, user_id: uuid.UUID) -> SpendingProfile:
        """Combines a per-currency card-payment average baseline with this
        month's category breakdown into one read-only "is this normal for
        this user" call, usable independently of evaluate_transaction().

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
        by_currency_history: dict[str, list[Transaction]] = {}
        for t in history:
            by_currency_history.setdefault(t.currency, []).append(t)
        by_currency = {
            currency: CurrencySpendingProfile(
                currency=currency,
                average_card_payment_amount=(sum((t.amount for t in items), Decimal("0")) / len(items)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                card_payment_history_count=len(items),
            )
            for currency, items in by_currency_history.items()
        }
        now = datetime.now(timezone.utc)
        spending = AnalyticsService(self.db).spending_by_type(user_id, now.year, now.month)
        return SpendingProfile(
            by_currency=by_currency,
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

    def save_agent_analysis(
        self,
        case: FraudCase,
        risk_level: FraudRiskLevel,
        explanation: str,
        **analysis_sections: Any,
    ) -> FraudCase:
        """Persists the Fraud Investigation Agent's qualitative output onto
        FraudCase.agent_analysis (JSON-serialized). Advisory only — never
        touches risk_score or status. Called only from the admin-triggered
        POST /fraud/cases/{id}/investigate endpoint (ai/fraud/agent.py),
        never automatically."""
        payload = FraudAgentAnalysisPublic(
            risk_level=risk_level,
            explanation=explanation,
            generated_at=datetime.now(timezone.utc),
            **analysis_sections,
        )
        case.agent_analysis = payload.model_dump_json()
        self.db.flush()
        return case

    def build_investigation_context(self, case_id: uuid.UUID) -> dict[str, Any]:
        """Read-only, deterministic evidence pack for an anti-fraud analyst.

        The LLM may summarize this data, but it must not calculate these
        values itself. Missing data is recorded as a data gap instead of being
        treated as suspicious evidence.
        """
        case = self.get_case(case_id)
        transaction = self.transactions.get_by_id(case.transaction_id)
        if transaction is None:
            raise NotFoundError("Fraud case transaction not found")

        flags = self.repository.list_flags_for_case(case.id)
        history = self.transactions.list_for_user(case.user_id, limit=100)
        # Anchored to the flagged transaction's own timestamp, not wall-clock
        # now — a case can stay open for review while the user keeps
        # transacting, and a payment made *after* the hold must never leak
        # into the baseline/merchant evidence used to explain the hold (the
        # same anchor _velocity_analysis() below already uses correctly).
        anchor = _as_aware_utc(transaction.created_at)
        historical_transactions = [
            t for t in history if t.id != transaction.id and _as_aware_utc(t.created_at) <= anchor
        ]
        # Scoped to the transaction's own type (and to what this user sent,
        # not received), mirroring _high_amount_flag()'s baseline: an admin
        # reviewing a held transfer must be shown the transfer history it was
        # actually measured against, not an unrelated card-payment average.
        # The dict keys below keep their original "card payment" names so the
        # admin UI and any cached agent_analysis rows stay readable.
        completed_same_type_history = [
            t
            for t in historical_transactions
            if t.type == transaction.type
            and t.status == TransactionStatus.COMPLETED
            and t.initiator_user_id == case.user_id
        ]
        merchant = self.merchants.get_by_id(transaction.merchant_id) if transaction.merchant_id is not None else None
        devices = self.get_known_devices(case.user_id)
        current_device = self.repository.get_latest_device_for_user(case.user_id)
        previous_cases = [previous for previous in self.repository.list_for_user(case.user_id) if previous.id != case.id]
        previous_case_details = self._previous_case_details(previous_cases, transaction)

        data_gaps: list[str] = []
        suspicious_signals = [f"{flag.code.value}: {flag.description}" for flag in flags]
        reassuring_signals: list[str] = []
        recommended_checks: list[str] = [
            "Verify whether the customer recognizes the merchant or counterparty.",
            "Review transactions immediately before and after the payment under review.",
        ]
        recommended_checks.extend(self._flag_review_checks(flags))

        if transaction.merchant_id is None:
            data_gaps.append("No merchant identifier is attached to this transaction.")
        elif merchant is None:
            data_gaps.append("Merchant details are unavailable for the transaction merchant_id.")
        if transaction.category_id is None:
            data_gaps.append("No transaction category is available.")
        if not devices:
            data_gaps.append("No known devices are recorded for this user.")
        if current_device is None:
            data_gaps.append("No active session device is available as a proxy for the payment device.")
        if not previous_cases:
            data_gaps.append("No previous fraud-case decisions are available for this user.")

        amount_baseline = self._amount_baseline(transaction, completed_same_type_history)
        if amount_baseline["sample_size"] < HIGH_AMOUNT_MIN_HISTORY:
            # Checked against the same-currency sample size, not the total
            # history count across all currencies — see _amount_baseline().
            data_gaps.append(
                f"Insufficient completed {_screened_currency(transaction)} {_type_label(transaction)} history "
                "for robust amount baselines."
            )
        ratio = amount_baseline.get("amount_to_average_ratio")
        if ratio is not None:
            if Decimal(str(ratio)) > HIGH_AMOUNT_MULTIPLIER:
                suspicious_signals.append(
                    f"Amount is {ratio}x the user's average completed {_type_label(transaction)}."
                )
            elif completed_same_type_history:
                reassuring_signals.append(
                    f"Amount is within the user's established completed {_type_label(transaction)} range."
                )

        merchant_analysis = self._merchant_analysis(transaction, historical_transactions, merchant, previous_case_details)
        if merchant_analysis["first_recorded_interaction"]:
            suspicious_signals.append("This is the first recorded interaction with this merchant.")
        elif merchant_analysis["previous_transaction_count"] > 0:
            reassuring_signals.append(
                f"User has {merchant_analysis['previous_transaction_count']} previous transaction(s) with this merchant."
            )
        if merchant_analysis["previous_fraud_cases_with_merchant"] > 0:
            suspicious_signals.append("Previous fraud cases involved the same merchant.")

        velocity_analysis = self._velocity_analysis(transaction, history)
        if velocity_analysis["near_identical_transactions_10m"] >= REWARD_ABUSE_MIN_COUNT:
            suspicious_signals.append("Near-identical same-merchant payments appear within ten minutes.")
        if velocity_analysis["windows"]["5m"]["count"] >= HIGH_VELOCITY_MIN_COUNT:
            suspicious_signals.append("Transaction volume in the previous five minutes is elevated.")

        device_analysis = self._device_analysis(current_device, devices, data_gaps)
        if current_device is not None:
            if current_device.trusted:
                reassuring_signals.append("Latest active device is marked trusted.")
            else:
                suspicious_signals.append("Latest active device is not marked trusted.")
            if current_device.mock_location and len(device_analysis["known_locations"]) > 1:
                reassuring_signals.append("Device location can be compared against prior known device locations.")

        historical_context = self._historical_context(previous_case_details, flags)
        if historical_context["previous_case_count"] > 0:
            suspicious_signals.append(f"User has {historical_context['previous_case_count']} previous fraud case(s).")
            recommended_checks.append("Compare this case with prior manual fraud decisions for the same customer.")

        if merchant_analysis["repeated_same_amount_count"] >= REWARD_ABUSE_MIN_COUNT:
            recommended_checks.append("Check whether repeated same-amount merchant payments are duplicate attempts.")
        if current_device is not None:
            recommended_checks.append("Confirm whether the latest active device belongs to the customer.")

        return {
            "case_overview": self._case_overview(case, transaction, flags, merchant),
            "behavioral_analysis": {
                "history_transaction_count": len(historical_transactions),
                "completed_card_payment_count": len(completed_same_type_history),
                "amount_baseline": amount_baseline,
                "transaction_counts": self._transaction_counts(transaction, history),
                "usual_transaction_types": self._top_values([t.type.value for t in completed_same_type_history]),
                "usual_merchant_ids": self._top_values(
                    [str(t.merchant_id) for t in completed_same_type_history if t.merchant_id]
                ),
                "usual_transaction_hours_utc": self._top_values(
                    [str(_as_aware_utc(t.created_at).hour) for t in completed_same_type_history]
                ),
            },
            "velocity_analysis": velocity_analysis,
            "merchant_analysis": merchant_analysis,
            "device_analysis": device_analysis,
            "historical_context": historical_context,
            "suspicious_signals": self._dedupe(suspicious_signals),
            "reassuring_signals": self._dedupe(reassuring_signals),
            "data_gaps": self._dedupe(data_gaps),
            "recommended_checks": self._dedupe(recommended_checks),
        }

    def _case_overview(
        self, case: FraudCase, transaction: Transaction, flags: list[FraudFlag], merchant
    ) -> dict[str, Any]:
        return {
            "case_id": str(case.id),
            "transaction_id": str(transaction.id),
            "transaction_amount": transaction.amount,
            "currency": transaction.currency,
            "transaction_type": transaction.type.value,
            "transaction_status": transaction.status.value,
            "description": transaction.description,
            "created_at": transaction.created_at,
            "deterministic_risk_score": case.risk_score,
            "case_status": case.status.value,
            "hold_amount": case.hold_amount,
            "merchant": self._merchant_summary(merchant),
            "counterparty_user_id": str(transaction.counterparty_user_id) if transaction.counterparty_user_id else None,
            "source_wallet_id": str(transaction.source_wallet_id) if transaction.source_wallet_id else None,
            "destination_wallet_id": str(transaction.destination_wallet_id) if transaction.destination_wallet_id else None,
            "card_id": str(transaction.card_id) if transaction.card_id else None,
            "flags": [
                {
                    "code": flag.code.value,
                    "points": flag.points,
                    "description": flag.description,
                }
                for flag in flags
            ],
        }

    def _amount_baseline(self, transaction: Transaction, completed_history: list[Transaction]) -> dict[str, Any]:
        """`completed_history` may span multiple currencies (callers build it
        from the user's full history); the baseline itself must only ever
        compare `transaction` against that same-currency subset — see module
        docstring. Amounts are the source-side ones (_screened_amount), so a
        cross-currency transfer is measured by what left the payer's wallet."""
        amount = _screened_amount(transaction)
        currency = _screened_currency(transaction)
        same_currency_history = [t for t in completed_history if _screened_currency(t) == currency]
        amounts = sorted(_screened_amount(t) for t in same_currency_history)
        if not amounts:
            return {
                "currency": currency,
                "average_completed_card_payment": None,
                "median_completed_card_payment": None,
                "largest_completed_card_payment": None,
                "amount_to_average_ratio": None,
                "amount_percentile": None,
                "sample_size": 0,
            }

        total = sum(amounts, Decimal("0"))
        average = (total / len(amounts)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        middle = len(amounts) // 2
        if len(amounts) % 2:
            median = amounts[middle]
        else:
            median = ((amounts[middle - 1] + amounts[middle]) / Decimal("2")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        ratio = None
        if average > 0:
            ratio = (amount / average).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        percentile = (
            (Decimal(sum(1 for item in amounts if item <= amount)) / Decimal(len(amounts)) * Decimal("100"))
            .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        )
        return {
            "currency": currency,
            "average_completed_card_payment": average,
            "median_completed_card_payment": median,
            "largest_completed_card_payment": amounts[-1],
            "amount_to_average_ratio": ratio,
            "amount_percentile": percentile,
            "sample_size": len(amounts),
        }

    def _transaction_counts(self, transaction: Transaction, history: list[Transaction]) -> dict[str, int]:
        windows = {
            "last_1h": timedelta(hours=1),
            "last_24h": timedelta(hours=24),
            "last_7d": timedelta(days=7),
            "last_30d": timedelta(days=30),
        }
        anchor = _as_aware_utc(transaction.created_at)
        return {
            name: sum(1 for item in history if anchor - window <= _as_aware_utc(item.created_at) <= anchor)
            for name, window in windows.items()
        }

    def _velocity_analysis(self, transaction: Transaction, history: list[Transaction]) -> dict[str, Any]:
        anchor = _as_aware_utc(transaction.created_at)
        windows = {
            "5m": timedelta(minutes=5),
            "10m": timedelta(minutes=10),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
        }
        window_results = {}
        for name, window in windows.items():
            items = [item for item in history if anchor - window <= _as_aware_utc(item.created_at) <= anchor]
            window_results[name] = {
                "count": len(items),
                "total_amount": sum((item.amount for item in items), Decimal("0")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                "same_merchant_count": sum(
                    1
                    for item in items
                    if transaction.merchant_id is not None and item.merchant_id == transaction.merchant_id
                ),
                "distinct_merchant_count": len({item.merchant_id for item in items if item.merchant_id is not None}),
            }

        ten_minute_items = [
            item
            for item in history
            if anchor - REWARD_ABUSE_WINDOW <= _as_aware_utc(item.created_at) <= anchor
        ]
        repeat_key = _repeat_key(transaction)
        near_identical_count = sum(
            1
            for item in ten_minute_items
            if repeat_key is not None
            and item.type == transaction.type
            and _repeat_key(item) == repeat_key
            and _screened_currency(item) == _screened_currency(transaction)
            and abs(_screened_amount(item) - _screened_amount(transaction)) < Decimal("0.01")
        )
        return {
            "windows": window_results,
            "near_identical_transactions_10m": near_identical_count,
            "rapid_merchant_switching_30m": window_results["30m"]["distinct_merchant_count"],
        }

    def _merchant_analysis(
        self,
        transaction: Transaction,
        historical_transactions: list[Transaction],
        merchant,
        previous_case_details: list[dict[str, Any]],
    ) -> dict[str, Any]:
        merchant_transactions = [
            item
            for item in historical_transactions
            if transaction.merchant_id is not None and item.merchant_id == transaction.merchant_id
        ]
        completed_amounts = [item.amount for item in merchant_transactions if item.status == TransactionStatus.COMPLETED]
        typical_amount = None
        if completed_amounts:
            typical_amount = (sum(completed_amounts, Decimal("0")) / len(completed_amounts)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        repeated_same_amount_count = sum(
            1
            for item in merchant_transactions
            if item.currency == transaction.currency and abs(item.amount - transaction.amount) < Decimal("0.01")
        )
        previous_fraud_cases_with_merchant = sum(
            1
            for detail in previous_case_details
            if transaction.merchant_id is not None and detail.get("merchant_id") == str(transaction.merchant_id)
        )
        return {
            "merchant": self._merchant_summary(merchant),
            "previous_transaction_count": len(merchant_transactions),
            "typical_completed_amount": typical_amount,
            "first_recorded_interaction": transaction.merchant_id is not None and not merchant_transactions,
            "repeated_same_amount_count": repeated_same_amount_count + 1 if transaction.merchant_id is not None else 0,
            "merchant_concentration_percent": self._merchant_concentration(transaction, historical_transactions),
            "previous_fraud_cases_with_merchant": previous_fraud_cases_with_merchant,
        }

    def _device_analysis(
        self, current_device: UserDevice | None, devices: list[UserDevice], data_gaps: list[str]
    ) -> dict[str, Any]:
        known_locations = sorted({device.mock_location for device in devices if device.mock_location})
        if not known_locations:
            data_gaps.append("No device location history is available.")
        if current_device is not None and not current_device.mock_location:
            data_gaps.append("Latest active device has no mock_location value.")
        return {
            "latest_active_device": self._device_summary(current_device),
            "known_device_count": len(devices),
            "trusted_device_count": sum(1 for device in devices if device.trusted),
            "known_locations": known_locations,
            "has_new_or_untrusted_active_device": current_device is not None and not current_device.trusted,
            "transaction_device_link_available": False,
        }

    def _historical_context(self, previous_case_details: list[dict[str, Any]], flags: list[FraudFlag]) -> dict[str, Any]:
        status_counts = Counter(detail["status"] for detail in previous_case_details)
        current_codes = {flag.code.value for flag in flags}
        recurring_flags = Counter(
            code for detail in previous_case_details for code in detail["flag_codes"] if code in current_codes
        )
        return {
            "previous_case_count": len(previous_case_details),
            "status_counts": dict(status_counts),
            "recurring_flags": dict(recurring_flags),
            "previous_cases": previous_case_details[:5],
        }

    def _previous_case_details(self, previous_cases: list[FraudCase], current_transaction: Transaction) -> list[dict[str, Any]]:
        details = []
        for previous in previous_cases:
            previous_transaction = self.transactions.get_by_id(previous.transaction_id)
            previous_flags = self.repository.list_flags_for_case(previous.id)
            details.append(
                {
                    "case_id": str(previous.id),
                    "transaction_id": str(previous.transaction_id),
                    "status": previous.status.value,
                    "risk_score": previous.risk_score,
                    "created_at": previous.created_at,
                    "decided_at": previous.decided_at,
                    "flag_codes": [flag.code.value for flag in previous_flags],
                    "amount": previous_transaction.amount if previous_transaction is not None else None,
                    "currency": previous_transaction.currency if previous_transaction is not None else None,
                    "merchant_id": str(previous_transaction.merchant_id)
                    if previous_transaction is not None and previous_transaction.merchant_id
                    else None,
                    "same_merchant": previous_transaction is not None
                    and current_transaction.merchant_id is not None
                    and previous_transaction.merchant_id == current_transaction.merchant_id,
                }
            )
        return details

    def _flag_review_checks(self, flags: list[FraudFlag]) -> list[str]:
        checks: list[str] = []
        flag_codes = {flag.code for flag in flags}
        if FraudFlagCode.HIGH_VELOCITY in flag_codes:
            checks.append("Inspect the short-window transaction timeline for a burst, retry loop, or account takeover pattern.")
            checks.append("Compare merchants and amounts in the burst instead of reviewing this payment in isolation.")
        if FraudFlagCode.REWARD_ABUSE_PATTERN in flag_codes:
            checks.append("Check whether same-amount same-merchant payments are legitimate duplicate checkout attempts.")
            checks.append("Review merchant cashback/reward eligibility for the repeated payments before clearing the case.")
        if FraudFlagCode.REPEATED_TRANSFER_PATTERN in flag_codes:
            checks.append("Check whether the repeated transfers to this account are duplicate submissions by the customer.")
            checks.append("Verify the customer knows the destination account holder and intended to send each transfer.")
        if FraudFlagCode.HIGH_AMOUNT in flag_codes:
            checks.append("Compare the held amount with this customer's largest previous completed card payments.")
        if FraudFlagCode.NEW_DEVICE in flag_codes:
            checks.append("Confirm whether the latest active device is recognized and has trusted prior activity.")
        if FraudFlagCode.UNUSUAL_COUNTRY in flag_codes:
            checks.append("Treat device location as a proxy only; verify whether the customer recently used this location.")
        if FraudFlagCode.UNUSUAL_TIME in flag_codes:
            checks.append("Review whether the UTC transaction time is unusual for this customer's own history.")
        return checks

    def _merchant_concentration(self, transaction: Transaction, historical_transactions: list[Transaction]) -> Decimal | None:
        merchant_transactions = [item for item in historical_transactions if item.merchant_id is not None]
        if transaction.merchant_id is None or not merchant_transactions:
            return None
        same_merchant = sum(1 for item in merchant_transactions if item.merchant_id == transaction.merchant_id)
        return (Decimal(same_merchant) / Decimal(len(merchant_transactions)) * Decimal("100")).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    def _merchant_summary(self, merchant) -> dict[str, Any] | None:
        if merchant is None:
            return None
        return {
            "id": str(merchant.id),
            "name": merchant.name,
            "category": merchant.category,
            "status": merchant.status.value,
            "verified": merchant.verified,
        }

    def _device_summary(self, device: UserDevice | None) -> dict[str, Any] | None:
        if device is None:
            return None
        return {
            "id": str(device.id),
            "device_name": device.device_name,
            "device_type": device.device_type,
            "browser": device.browser,
            "operating_system": device.operating_system,
            "mock_location": device.mock_location,
            "trusted": device.trusted,
            "first_seen_at": device.first_seen_at,
            "last_seen_at": device.last_seen_at,
        }

    def _top_values(self, values: list[str], limit: int = 3) -> list[dict[str, Any]]:
        return [{"value": value, "count": count} for value, count in Counter(values).most_common(limit)]

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        result = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

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

    def _high_amount_flag(self, transaction: Transaction, history: list[Transaction]) -> FlagHit | None:
        # Same-currency only — see module docstring. A user with no prior
        # history in this transaction's currency simply has no baseline to
        # compare against, so this falls through the same insufficient-
        # history path as a brand-new user (return None), rather than ever
        # falling back to a cross-currency average.
        #
        # Also same-TYPE only: a transfer is compared against the user's own
        # transfer history and a card payment against their card payments.
        # Somebody whose card spending averages 50 RON isn't thereby unusual
        # for moving 300 RON between their own accounts, and vice versa —
        # blending the two would produce a baseline that describes neither
        # behavior. The initiator filter matters for transfers specifically:
        # list_for_user also returns transfers this user *received* (they own
        # the destination wallet), and money coming in says nothing about
        # what's normal for them to send.
        baseline = [
            t
            for t in history
            if t.type == transaction.type
            and t.status == TransactionStatus.COMPLETED
            and t.initiator_user_id == transaction.initiator_user_id
            and t.id != transaction.id
            and _screened_currency(t) == _screened_currency(transaction)
        ]
        if len(baseline) < HIGH_AMOUNT_MIN_HISTORY:
            return None

        amount = _screened_amount(transaction)
        average = sum((_screened_amount(t) for t in baseline), Decimal("0")) / len(baseline)
        if average <= 0:
            return None
        ratio = amount / average
        if ratio <= HIGH_AMOUNT_MULTIPLIER:
            return None

        points = _scaled_points(
            ratio - HIGH_AMOUNT_MULTIPLIER, HIGH_AMOUNT_BASE_POINTS, HIGH_AMOUNT_POINTS_PER_EXTRA_MULTIPLE, HIGH_AMOUNT_MAX_POINTS
        )
        return (
            FraudFlagCode.HIGH_AMOUNT,
            points,
            f"{amount} is {ratio.quantize(Decimal('0.1'))}x this user's average "
            f"{_type_label(transaction)} ({average.quantize(Decimal('0.01'))})",
        )

    def _velocity_and_repeat_flags(
        self,
        transaction: Transaction,
        history: list[Transaction],
        *,
        batch_sibling_ids: frozenset[uuid.UUID] | None = None,
    ) -> list[FlagHit]:
        """HIGH_VELOCITY plus whichever repeat-pattern flag fits this
        transaction's type — REWARD_ABUSE_PATTERN for card payments (repeats
        to one merchant), REPEATED_TRANSFER_PATTERN for transfers (repeats to
        one destination wallet). Both are the same underlying shape and share
        the REWARD_ABUSE_* calibration below; only the counterparty they key
        on and the wording differ.

        `batch_sibling_ids` are the other transactions IbanTransferService.
        create_bulk_transfer already created earlier in the same bulk submit
        — excluded from velocity_count only (matching/repeat-pattern
        detection still sees them) so one deliberate multi-row batch doesn't
        rack up HIGH_VELOCITY against itself. A real burst of *other*
        activity around it still counts and can still cross the threshold."""
        flags: list[FlagHit] = []
        now = _as_aware_utc(transaction.created_at or datetime.now(timezone.utc))
        lookback = max(HIGH_VELOCITY_WINDOW, REWARD_ABUSE_WINDOW)
        recent = [
            t
            for t in self.get_recent_activity(
                transaction.initiator_user_id, window=lookback, as_of=now, history=history
            )
            # CASHBACK is money the system credits back as a side effect of a
            # CARD_PAYMENT, not a separate user action — without this filter
            # every cashback-eligible payment counts twice toward velocity
            # (the payment, then its own cashback a moment later), same
            # rationale as analytics' _is_real_spend excluding CASHBACK.
            #
            # The initiator filter keeps *incoming* transfers out of a user's
            # velocity count: list_for_user also returns transactions they
            # merely received, and being paid by other people is not this
            # user transacting rapidly.
            if t.id != transaction.id
            and t.type != TransactionType.CASHBACK
            and t.initiator_user_id == transaction.initiator_user_id
        ]

        repeat_key = _repeat_key(transaction)
        matching = [
            t
            for t in recent
            if repeat_key is not None
            and t.type == transaction.type
            and _repeat_key(t) == repeat_key
            and _as_aware_utc(t.created_at) >= now - REWARD_ABUSE_WINDOW
            and _screened_currency(t) == _screened_currency(transaction)
            and abs(_screened_amount(t) - _screened_amount(transaction)) < Decimal("0.01")
        ]
        matching_ids = {t.id for t in matching}

        velocity_count = sum(
            1
            for t in recent
            if t.id not in matching_ids
            and _as_aware_utc(t.created_at) >= now - HIGH_VELOCITY_WINDOW
            and (batch_sibling_ids is None or t.id not in batch_sibling_ids)
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
        if repeat_key is not None and total_matching >= REWARD_ABUSE_MIN_COUNT:
            minutes = REWARD_ABUSE_WINDOW.seconds // 60
            points = _scaled_points(
                Decimal(total_matching - REWARD_ABUSE_MIN_COUNT),
                REWARD_ABUSE_BASE_POINTS,
                REWARD_ABUSE_POINTS_PER_EXTRA,
                REWARD_ABUSE_MAX_POINTS,
            )
            if transaction.type == TransactionType.TRANSFER:
                flags.append(
                    (
                        FraudFlagCode.REPEATED_TRANSFER_PATTERN,
                        points,
                        f"{total_matching} near-identical transfers to the same account within {minutes} minutes",
                    )
                )
            else:
                flags.append(
                    (
                        FraudFlagCode.REWARD_ABUSE_PATTERN,
                        points,
                        f"{total_matching} near-identical payments to the same merchant within {minutes} minutes",
                    )
                )
        return flags

    def _unusual_time_flag(self, transaction: Transaction, history: list[Transaction]) -> FlagHit | None:
        now = _as_aware_utc(transaction.created_at or datetime.now(timezone.utc))
        hour = now.hour
        if not (UNUSUAL_TIME_WINDOW_START_HOUR <= hour < UNUSUAL_TIME_WINDOW_END_HOUR):
            return None

        # Precedent is looked for within the same transaction type (and only
        # among transactions this user initiated): somebody who routinely
        # transfers at 03:00 but has never made a night card payment has
        # established that the hour is normal *for transferring*, and money
        # arriving overnight from someone else establishes nothing at all.
        precedent = [
            t
            for t in history
            if t.type == transaction.type
            and t.status == TransactionStatus.COMPLETED
            and t.initiator_user_id == transaction.initiator_user_id
            and t.id != transaction.id
        ]
        has_night_precedent = any(
            UNUSUAL_TIME_WINDOW_START_HOUR <= _as_aware_utc(t.created_at).hour < UNUSUAL_TIME_WINDOW_END_HOUR
            for t in precedent
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
        self,
        transaction: Transaction,
        wallet: Wallet,
        score: Decimal,
        flags: list[FlagHit],
        *,
        batch_reference: str | None = None,
    ) -> FraudCase:
        # The hold is always the SOURCE side: on a cross-currency transfer
        # `transaction.amount` is what the recipient would receive in their
        # currency, which is not what leaves this wallet. Reserving that
        # figure would take the wrong number of the wrong currency out of the
        # payer's balance. See _screened_amount().
        hold_amount = _screened_amount(transaction)
        wallet.available_balance -= hold_amount
        wallet.reserved_balance += hold_amount
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.HOLD,
                amount=hold_amount,
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
                hold_amount=hold_amount,
                batch_reference=batch_reference,
            )
        )
        for code, points, description in flags:
            self.repository.add_flag(FraudFlag(fraud_case_id=case.id, code=code, points=points, description=description))

        # Deterministic step, not an LLM decision (architecture.md §44 rule
        # 3 / CLAUDE.md §12): freezing the card that made the flagged
        # payment happens here, in the same rule engine that computed the
        # score, at the same moment the wallet hold is placed. Only an
        # admin can clear it afterwards, via activate_card() below.
        if transaction.card_id is not None:
            CardService(self.db).freeze_for_fraud_hold(transaction.card_id)

        self.db.flush()
        return case

    def _credit_destination_if_transfer(self, transaction: Transaction) -> None:
        """Completes the *other half* of an approved transfer.

        A HOLD only ever moves money out of the payer's wallet. For a card
        payment that's the whole story — the money leaves the bank. A
        transfer between two EasyB wallets has a second leg the hold never
        touched, so approving one without crediting the destination would
        make the money disappear from the system. This mirrors
        TransactionService._settle()'s CREDIT leg, including its best-effort
        recipient notification.

        Credits `transaction.amount`, not `case.hold_amount`: on a
        cross-currency transfer the recipient gets the target-side amount at
        the rate already priced onto the transaction when it was created, so
        how long an admin sits on the case can't change what they receive.
        """
        if transaction.destination_wallet_id is None:
            return

        destination = self.wallets.get_by_id_for_update(transaction.destination_wallet_id)
        if destination is None:
            raise NotFoundError("Transfer destination wallet not found")

        destination.available_balance += transaction.amount
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=destination.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=transaction.amount,
                currency=destination.currency,
                balance_after=destination.available_balance,
            )
        )

        # Best-effort, same as _settle(): a notification failure must never
        # make an otherwise-successful approval look like it failed.
        try:
            NotificationsService(self.db).create(
                destination.user_id,
                type="TRANSACTION",
                title="Money received",
                message=f"You received {transaction.amount} {destination.currency}.",
                related_transaction_id=transaction.id,
            )
        except Exception:
            logger.exception(
                "Failed to create 'money received' notification for approved transaction %s", transaction.id
            )

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
        self._credit_destination_if_transfer(transaction)
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

        # The transaction only just became COMPLETED here — it was skipped
        # by TransactionService.create_card_payment's own auto-sync (see
        # that method's docstring) since it was PENDING_REVIEW at the time.
        # Sync now so an approved-after-hold payment earns points/cashback
        # immediately too, not only the next time something else syncs.
        MerchantService(self.db).sync_purchases_from_transactions(transaction.initiator_user_id)
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

    def get_frozen_card_for_case(self, case: FraudCase) -> Card | None:
        """The card behind this case's transaction, only if it's still
        frozen with CardFreezeReason.FRAUD_HOLD — None once it's been
        reactivated, or if the flagged transaction wasn't a card payment at
        all. Backs both the admin panel's "Activate card" button (to_detail
        below) and activate_card()'s own guard."""
        transaction = self.transactions.get_by_id(case.transaction_id)
        if transaction is None or transaction.card_id is None:
            return None
        card = self.cards.get_by_id(transaction.card_id)
        if card is None or card.status != CardStatus.FROZEN or card.freeze_reason != CardFreezeReason.FRAUD_HOLD:
            return None
        return card

    def activate_card(self, case: FraudCase, admin: User) -> Card:
        """Clears a fraud-triggered card freeze — always a separate, manual
        admin action from approve()/reject() above (CLAUDE.md §13: the
        admin decides, never the AI, and never automatically). Deliberately
        requires the flagged transaction to already be decided: reactivating
        the card while the case is still PENDING_REVIEW would let the
        customer place new payments on it before anyone has ruled on the
        payment that triggered the hold in the first place."""
        if case.status == FraudCaseStatus.PENDING_REVIEW:
            raise ConflictError("Decide the flagged transaction (approve or reject) before reactivating the card")
        card = self.get_frozen_card_for_case(case)
        if card is None:
            raise NotFoundError("No card with an active fraud hold is linked to this case")
        return CardService(self.db).activate_card_after_fraud_hold(card.id, admin.id)

    def list_pending(self) -> list[FraudCaseSummary]:
        return [self._to_summary(case) for case in self.repository.list_pending()]

    def to_detail(self, case: FraudCase) -> FraudCaseDetail:
        transaction = self.transactions.get_by_id(case.transaction_id)
        flags = self.repository.list_flags_for_case(case.id)
        agent_analysis = (
            FraudAgentAnalysisPublic.model_validate_json(case.agent_analysis) if case.agent_analysis else None
        )
        frozen_card = self.get_frozen_card_for_case(case)
        return FraudCaseDetail(
            id=case.id,
            transaction_id=case.transaction_id,
            user_id=case.user_id,
            risk_score=case.risk_score,
            status=case.status,
            hold_amount=case.hold_amount,
            # The hold sits in the SOURCE wallet's currency, which differs
            # from transaction.currency on a cross-currency transfer.
            hold_currency=_screened_currency(transaction),
            created_at=case.created_at,
            flag_codes=[flag.code for flag in flags],
            batch_reference=case.batch_reference,
            decided_by_admin_id=case.decided_by_admin_id,
            decided_at=case.decided_at,
            flags=[FraudFlagPublic(id=f.id, code=f.code, points=f.points, description=f.description) for f in flags],
            transaction_amount=transaction.amount,
            transaction_currency=transaction.currency,
            transaction_description=transaction.description,
            transaction_created_at=transaction.created_at,
            agent_analysis=agent_analysis,
            frozen_card=(
                FrozenCardPublic(
                    id=frozen_card.id,
                    last_four=frozen_card.last_four,
                    masked_pan=frozen_card.masked_pan,
                    frozen_at=frozen_card.frozen_at,
                )
                if frozen_card is not None
                else None
            ),
            card_hold_notice=CARD_ACTIVATION_SAFETY_NOTICE if frozen_card is not None else None,
        )

    def _to_summary(self, case: FraudCase) -> FraudCaseSummary:
        flags = self.repository.list_flags_for_case(case.id)
        transaction = self.transactions.get_by_id(case.transaction_id)
        return FraudCaseSummary(
            id=case.id,
            transaction_id=case.transaction_id,
            user_id=case.user_id,
            risk_score=case.risk_score,
            status=case.status,
            hold_amount=case.hold_amount,
            hold_currency=_screened_currency(transaction) if transaction is not None else "RON",
            created_at=case.created_at,
            flag_codes=[flag.code for flag in flags],
            batch_reference=case.batch_reference,
        )
