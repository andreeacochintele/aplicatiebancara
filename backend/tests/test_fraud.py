import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.auth.models import SessionStatus, UserDevice, UserSession
from app.cards.models import CardStatus, CardType
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.enums import UserRole
from app.core.exceptions import ConflictError
from app.fraud.models import FraudCase, FraudCaseStatus, FraudFlagCode
from app.fraud.schemas import FraudRiskLevel
from app.fraud.service import FraudService
from app.merchants.schemas import CashbackOfferCreate, MerchantCreate
from app.merchants.service import MerchantService
from app.rewards.service import RewardsService
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.transactions.schemas import CardPaymentCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="fraud-user@example.com", password="Sup3rSecret!", first_name="Fraud", last_name="User")
    )


def _admin(db_session, email="fraud-admin@example.com"):
    return UserService(db_session).create_user(
        UserCreate(email=email, password="Sup3rSecret!", first_name="Admin", last_name="User")
    )


def _wallet(db_session, user_id, balance=Decimal("1000.00")):
    wallet = WalletService(db_session).create_wallet(user_id, WalletCreate(currency="RON"))
    wallet.available_balance = balance
    db_session.flush()
    return wallet


def _card(db_session, user_id, wallet_id, card_type=CardType.DEBIT):
    return CardService(db_session).create_card(user_id, CardCreate(type=card_type, default_wallet_id=wallet_id))


def _merchant(db_session, name="Nike"):
    return MerchantService(db_session).create_merchant(MerchantCreate(name=name, category="Retail", verified=True))


def _device(db_session, user_id, *, trusted, location=None, device_name="Device", active_at=None):
    device = UserDevice(
        user_id=user_id, device_name=device_name, device_type="mobile", trusted=trusted, mock_location=location
    )
    db_session.add(device)
    db_session.flush()
    activity = active_at or datetime.now(timezone.utc)
    session = UserSession(
        user_id=user_id,
        device_id=device.id,
        token_hash=f"hash-{device.id}",
        last_activity_at=activity,
        expires_at=activity + timedelta(days=1),
        status=SessionStatus.ACTIVE,
    )
    db_session.add(session)
    db_session.flush()
    return device


def _completed_card_payment(db_session, user_id, amount, merchant_id=None, created_at=None, currency="RON"):
    transaction = Transaction(
        initiator_user_id=user_id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=amount,
        currency=currency,
        merchant_id=merchant_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction


def _pending_transaction(user_id, wallet_id, amount, merchant_id=None, created_at=None, currency="RON"):
    return Transaction(
        id=uuid.uuid4(),
        initiator_user_id=user_id,
        source_wallet_id=wallet_id,
        merchant_id=merchant_id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.PROCESSING,
        amount=amount,
        currency=currency,
        created_at=created_at or datetime.now(timezone.utc),
    )


def _create_blocked_payment(db_session, seeded_user, amount=Decimal("500.00"), card_type=CardType.DEBIT):
    """3x50 RON baseline + an untrusted device -> a 10x-average HIGH_AMOUNT
    (15 base + 8*7 over-minimum = 71, capped at 70 - see FIX 2's raised
    HIGH_AMOUNT_MAX_POINTS) + NEW_DEVICE (25) = 95 base, combined with the
    2-flag weighted-combination multiplier (x1.15) = 109.25, which crosses
    the 65-point threshold."""
    wallet = _wallet(db_session, seeded_user.id, balance=Decimal("1000.00"))
    card = _card(db_session, seeded_user.id, wallet.id, card_type=card_type)
    merchant = _merchant(db_session)
    _device(db_session, seeded_user.id, trusted=False)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("50.00"))

    transaction = TransactionService(db_session).create_card_payment(
        seeded_user.id,
        CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=amount, cvv=card.mock_cvv),
    )
    case = db_session.query(FraudCase).filter(FraudCase.transaction_id == transaction.id).one()
    return transaction, wallet, card, case


def test_evaluate_with_no_signals_does_not_block(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"))

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.blocked is False
    assert decision.score == Decimal("0")
    assert transaction.fraud_score == Decimal("0")


def test_untrusted_device_flags_but_does_not_block_alone(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    _device(db_session, seeded_user.id, trusted=False)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"))

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.blocked is False
    assert decision.score == Decimal("25")


def test_trusted_known_device_does_not_flag(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    _device(db_session, seeded_user.id, trusted=True, location="Romania", active_at=now - timedelta(days=5))
    _device(db_session, seeded_user.id, trusted=True, location="Romania", device_name="Phone2", active_at=now)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"), created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


def test_unusual_country_flags_when_location_not_previously_seen(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    _device(db_session, seeded_user.id, trusted=True, location="Romania", device_name="Laptop", active_at=now - timedelta(days=5))
    _device(db_session, seeded_user.id, trusted=True, location="France", device_name="Phone", active_at=now)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"), created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("20")


def test_high_amount_flags_relative_to_users_average(db_session, seeded_user):
    """400 is exactly 4x the 100 average -> 1 multiple past the minimum
    trigger ratio (>3x): 15 base + 8*1 = 23 (see FIX 2's recalibrated
    HIGH_AMOUNT_POINTS_PER_EXTRA_MULTIPLE)."""
    wallet = _wallet(db_session, seeded_user.id)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("100.00"))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("400.00"))

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("23")


def test_high_amount_does_not_flag_without_enough_history(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    _completed_card_payment(db_session, seeded_user.id, Decimal("100.00"))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("5000.00"))

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


# ---- FIX 1: HIGH_AMOUNT's baseline is per-currency, never blended across a
# multi-currency wallet holder's history ----


def test_high_amount_baseline_is_scoped_to_the_transactions_currency(db_session, seeded_user):
    """A user with a much larger RON history must not have a genuinely
    high-value USD payment scored against a blended RON+USD average - it's
    scored only against this user's own USD history. Before FIX 1, the
    blended average here (RON+USD summed and divided by 6) would have put
    this 40.00 USD payment under the 3x trigger ratio entirely, scoring 0."""
    wallet = _wallet(db_session, seeded_user.id)
    # Spread well outside HIGH_VELOCITY_WINDOW/REWARD_ABUSE_WINDOW so only
    # the currency-scoped HIGH_AMOUNT baseline is under test here.
    now = datetime.now(timezone.utc)
    for i in range(3):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("100.00"), currency="RON", created_at=now - timedelta(days=10 + i)
        )
    for i in range(3):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("10.00"), currency="USD", created_at=now - timedelta(days=20 + i)
        )
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("40.00"), currency="USD", created_at=now)  # 4x USD average

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("23")  # 15 base + 8*1, scored against the 10.00 USD average


def test_high_amount_does_not_flag_a_users_first_payment_in_a_new_currency(db_session, seeded_user):
    """No same-currency history yet -> no baseline to compare against, so
    this falls through the same insufficient-history path as a brand-new
    user (documented fallback) rather than crashing or ever falling back to
    a cross-currency average."""
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    # Spread well outside HIGH_VELOCITY_WINDOW so only the currency fallback
    # behavior is under test here.
    for i in range(5):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("10.00"), currency="RON", created_at=now - timedelta(days=10 + i)
        )
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("5000.00"), currency="USD", created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


def test_high_velocity_flags_five_transactions_in_five_minutes(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    for _ in range(4):
        _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"), created_at=now - timedelta(minutes=1))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("10.00"), created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("30")


def test_reward_abuse_pattern_flags_three_near_identical_payments(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    merchant = _merchant(db_session)
    now = datetime.now(timezone.utc)
    for _ in range(2):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("25.00"), merchant_id=merchant.id, created_at=now - timedelta(minutes=2)
        )
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("25.00"), merchant_id=merchant.id, created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("35")


def test_identical_payment_burst_scores_abuse_pattern_only_not_velocity_too(db_session, seeded_user):
    """A burst of near-identical repeats to one merchant is a single
    underlying behavior — HIGH_VELOCITY must not also fire off the exact
    same transactions REWARD_ABUSE_PATTERN already counted."""
    wallet = _wallet(db_session, seeded_user.id)
    merchant = _merchant(db_session)
    now = datetime.now(timezone.utc)
    for _ in range(4):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("37.00"), merchant_id=merchant.id, created_at=now - timedelta(minutes=1)
        )
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("37.00"), merchant_id=merchant.id, created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    # 5 near-identical payments total -> 2 over the minimum trigger count of 3,
    # so 35 base + 10*2 = 55 (still under the 70 cap).
    assert decision.score == Decimal("55")


def test_velocity_still_flags_the_non_matching_activity_around_a_repeat_pattern(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    merchant = _merchant(db_session)
    now = datetime.now(timezone.utc)
    for _ in range(2):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("37.00"), merchant_id=merchant.id, created_at=now - timedelta(minutes=1)
        )
    for i in range(4):
        _completed_card_payment(db_session, seeded_user.id, Decimal(f"{5 + i}.00"), created_at=now - timedelta(minutes=1))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("37.00"), merchant_id=merchant.id, created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    # matching = 2 prior + this one = 3 -> REWARD_ABUSE_PATTERN at its minimum
    # trigger (base 35 points, recalibrated tighter - see the constant's
    # docstring). velocity = the 4 unrelated transactions (2 matching ones
    # excluded) + this one = 5 -> HIGH_VELOCITY at its minimum trigger too
    # (base 30 points, also recalibrated tighter) - still fires on the
    # genuinely separate activity, proving the matching_ids exclusion in
    # _velocity_and_abuse_flags still works post-recalibration. Two flags
    # co-occurring: (35 + 30) * 1.15 = 74.75 - with both flags tightened,
    # two bare-minimum-trigger flags now cross the 65-point threshold
    # together, where the pre-recalibration numbers (20 + 15) * 1.15 = 40.25
    # did not.
    assert decision.score == Decimal("74.75")
    assert decision.blocked is True


def test_transactions_with_no_merchant_never_match_each_other_for_abuse_pattern(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    for _ in range(2):
        _completed_card_payment(db_session, seeded_user.id, Decimal("25.00"), created_at=now - timedelta(minutes=2))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("25.00"), created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


def test_reward_abuse_pattern_ignores_same_amount_payments_in_a_different_currency(db_session, seeded_user):
    """FIX 1: REWARD_ABUSE_PATTERN's near-identical-amount matching is also
    currency-scoped - a RON 25.00 and a USD 25.00 payment are not the same
    amount, they just happen to share a numeral."""
    wallet = _wallet(db_session, seeded_user.id)
    merchant = _merchant(db_session)
    now = datetime.now(timezone.utc)
    for _ in range(2):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("25.00"), merchant_id=merchant.id,
            created_at=now - timedelta(minutes=2), currency="USD",
        )
    transaction = _pending_transaction(
        seeded_user.id, wallet.id, Decimal("25.00"), merchant_id=merchant.id, created_at=now, currency="RON"
    )

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


def test_create_card_payment_holds_funds_when_score_crosses_threshold(db_session, seeded_user):
    transaction, wallet, _card, case = _create_blocked_payment(db_session, seeded_user)

    assert transaction.status == TransactionStatus.PENDING_REVIEW
    assert transaction.fraud_score == Decimal("109.25")
    assert wallet.available_balance == Decimal("500.00")
    assert wallet.reserved_balance == Decimal("500.00")

    ledger_types = [entry.entry_type.value for entry in transaction.ledger_entries]
    assert ledger_types == ["HOLD"]

    assert case.status == FraudCaseStatus.PENDING_REVIEW
    assert case.risk_score == Decimal("109.25")
    assert case.hold_amount == Decimal("500.00")
    assert {flag.code for flag in case.flags} == {FraudFlagCode.NEW_DEVICE, FraudFlagCode.HIGH_AMOUNT}


def test_approve_debits_reserved_funds_completes_transaction_and_consumes_one_time_card(db_session, seeded_user):
    transaction, wallet, card, case = _create_blocked_payment(db_session, seeded_user, card_type=CardType.ONE_TIME)
    admin = _admin(db_session)

    approved = FraudService(db_session).approve(case, admin)

    assert approved.status == FraudCaseStatus.APPROVED
    assert approved.decided_by_admin_id == admin.id
    assert approved.decided_at is not None
    assert transaction.status == TransactionStatus.COMPLETED
    assert transaction.completed_at is not None
    assert wallet.reserved_balance == Decimal("0.00")
    assert wallet.available_balance == Decimal("500.00")  # unchanged since the HOLD already moved it out
    assert card.one_time_remaining == 0
    assert card.status == CardStatus.CANCELLED

    ledger_types = [entry.entry_type.value for entry in transaction.ledger_entries]
    assert ledger_types == ["HOLD", "DEBIT"]


def test_approve_syncs_rewards_for_the_now_completed_transaction(db_session, seeded_user):
    """Regression for a live report: a payment held for fraud review and
    later approved by an admin must earn cashback/points too. It was
    skipped by create_card_payment's own auto-sync (see that method's
    docstring) since the transaction was still PENDING_REVIEW, not
    COMPLETED, at the time create_card_payment returned."""
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Booking.com", category="Travel", verified=True))
    today = date.today()
    merchant_service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(
            cashback_percent=Decimal("4"), start_date=today - timedelta(days=1), end_date=today + timedelta(days=30)
        ),
    )

    wallet = _wallet(db_session, seeded_user.id, balance=Decimal("1000.00"))
    card = _card(db_session, seeded_user.id, wallet.id)
    _device(db_session, seeded_user.id, trusted=False)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("50.00"))

    transaction = TransactionService(db_session).create_card_payment(
        seeded_user.id,
        CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("500.00"), cvv=card.mock_cvv),
    )
    case = db_session.query(FraudCase).filter(FraudCase.transaction_id == transaction.id).one()
    assert transaction.status == TransactionStatus.PENDING_REVIEW

    # Not synced yet while held - create_card_payment's own auto-sync only
    # runs on its COMPLETED path, which this payment never reached.
    assert RewardsService(db_session).get_account(seeded_user.id).lifetime_points_earned == 0

    admin = _admin(db_session)
    FraudService(db_session).approve(case, admin)

    assert transaction.status == TransactionStatus.COMPLETED
    account = RewardsService(db_session).get_account(seeded_user.id)
    assert account.lifetime_points_earned == 500  # 500 RON * 1x base rate (REGULAR tier)
    assert wallet.available_balance == Decimal("520.00")  # 500 left after the hold's debit + 20 cashback (4% of 500)


def test_reject_releases_the_hold_back_to_available_balance(db_session, seeded_user):
    transaction, wallet, _card, case = _create_blocked_payment(db_session, seeded_user)
    admin = _admin(db_session)

    rejected = FraudService(db_session).reject(case, admin)

    assert rejected.status == FraudCaseStatus.REJECTED
    assert transaction.status == TransactionStatus.REJECTED
    assert wallet.reserved_balance == Decimal("0.00")
    assert wallet.available_balance == Decimal("1000.00")

    ledger_types = [entry.entry_type.value for entry in transaction.ledger_entries]
    assert ledger_types == ["HOLD", "RELEASE"]


def test_deciding_an_already_decided_case_raises_conflict(db_session, seeded_user):
    _transaction, _wallet, _card, case = _create_blocked_payment(db_session, seeded_user)
    admin = _admin(db_session)
    service = FraudService(db_session)
    service.approve(case, admin)

    with pytest.raises(ConflictError):
        service.reject(case, admin)


def test_list_pending_and_detail_expose_flags(db_session, seeded_user):
    transaction, _wallet, _card, _case = _create_blocked_payment(db_session, seeded_user)

    service = FraudService(db_session)
    pending = service.list_pending()

    assert len(pending) == 1
    assert pending[0].transaction_id == transaction.id
    assert set(pending[0].flag_codes) == {FraudFlagCode.NEW_DEVICE, FraudFlagCode.HIGH_AMOUNT}

    detail = service.to_detail(service.get_case(pending[0].id))
    assert detail.transaction_amount == Decimal("500.00")
    assert detail.transaction_currency == "RON"
    assert len(detail.flags) == 2


def test_build_investigation_context_exposes_structured_evidence(db_session, seeded_user):
    _transaction, _wallet, _card, case = _create_blocked_payment(db_session, seeded_user)

    context = FraudService(db_session).build_investigation_context(case.id)

    assert context["case_overview"]["deterministic_risk_score"] == Decimal("109.25")
    assert context["case_overview"]["transaction_amount"] == Decimal("500.00")
    assert {flag["code"] for flag in context["case_overview"]["flags"]} == {"NEW_DEVICE", "HIGH_AMOUNT"}
    assert context["behavioral_analysis"]["amount_baseline"]["average_completed_card_payment"] == Decimal("50.00")
    assert context["behavioral_analysis"]["amount_baseline"]["amount_to_average_ratio"] == Decimal("10.0")
    assert context["merchant_analysis"]["first_recorded_interaction"] is True
    assert context["device_analysis"]["latest_active_device"]["trusted"] is False
    assert any("NEW_DEVICE" in signal for signal in context["suspicious_signals"])
    assert "No transaction category is available." in context["data_gaps"]


# ---- proportional scaling: HIGH_AMOUNT points grow with how far over the
# minimum trigger ratio the payment is, up to a cap ----


def test_high_amount_points_scale_with_ratio_over_average(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("100.00"))

    at_minimum = _pending_transaction(seeded_user.id, wallet.id, Decimal("400.00"))  # 4x average
    further_over = _pending_transaction(seeded_user.id, wallet.id, Decimal("600.00"))  # 6x average

    score_at_minimum = FraudService(db_session).evaluate_transaction(at_minimum, wallet).score
    score_further_over = FraudService(db_session).evaluate_transaction(further_over, wallet).score

    assert score_at_minimum == Decimal("23")  # 15 base + 8*1
    assert score_further_over == Decimal("39")  # 15 base + 8*3
    assert score_further_over > score_at_minimum


def test_high_amount_points_cap_at_max_for_extreme_outliers(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("5000.00"))  # 500x average

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("70")  # capped, not 15 + 8*497


# ---- FIX 2: HIGH_AMOUNT and HIGH_VELOCITY's raised caps let a single,
# sufficiently extreme signal cross FRAUD_SCORE_THRESHOLD (65) entirely on
# its own, without needing a second co-occurring flag ----


def test_extreme_high_amount_alone_crosses_threshold_without_a_second_flag(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    daytime = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("50.00"), created_at=daytime - timedelta(days=1))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("500.00"), created_at=daytime)  # 10x average

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    # 15 base + 8*7 = 71, capped at 70 -> a single HIGH_AMOUNT flag alone (no
    # device, no velocity signal) crosses the 65-point threshold by itself.
    assert decision.score == Decimal("70")
    assert decision.blocked is True
    assert {flag.code for flag in decision.case.flags} == {FraudFlagCode.HIGH_AMOUNT}


def test_extreme_velocity_burst_alone_crosses_threshold_without_a_second_flag(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    daytime = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    for _ in range(14):
        _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"), created_at=daytime)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("10.00"), created_at=daytime)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    # total_velocity = 14 + 1 = 15, 10 over the minimum trigger count of 5:
    # 30 base + 12*10 = 150, capped at 70 -> a single HIGH_VELOCITY flag alone
    # (amount stays at 1x the user's average, so HIGH_AMOUNT never fires)
    # crosses the 65-point threshold by itself.
    assert decision.score == Decimal("70")
    assert decision.blocked is True
    assert {flag.code for flag in decision.case.flags} == {FraudFlagCode.HIGH_VELOCITY}


def test_extreme_reward_abuse_burst_alone_crosses_threshold_without_a_second_flag(db_session, seeded_user):
    """Reported live: 8 identical repeats to the same merchant didn't cross
    the threshold (score capped at the old 40) - REWARD_ABUSE_PATTERN's cap
    is raised the same way HIGH_AMOUNT/HIGH_VELOCITY's were, so a large
    enough burst can hold a transaction on its own too."""
    wallet = _wallet(db_session, seeded_user.id)
    merchant = _merchant(db_session)
    now = datetime.now(timezone.utc)
    for _ in range(11):
        _completed_card_payment(
            db_session, seeded_user.id, Decimal("50.00"), merchant_id=merchant.id, created_at=now - timedelta(minutes=1)
        )
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"), merchant_id=merchant.id, created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    # total_matching = 11 + 1 = 12, 9 over the minimum trigger count of 3:
    # 35 base + 10*9 = 125, capped at 70 -> a single REWARD_ABUSE_PATTERN flag
    # alone crosses the 65-point threshold by itself. (The 11 matching
    # history payments are excluded from HIGH_VELOCITY's own count, so it
    # never co-fires - see _velocity_and_abuse_flags.)
    assert decision.score == Decimal("70")
    assert decision.blocked is True
    assert {flag.code for flag in decision.case.flags} == {FraudFlagCode.REWARD_ABUSE_PATTERN}


# ---- UNUSUAL_TIME: a night-window payment with no precedent of this user
# transacting in that window before ----


def test_unusual_time_flags_night_payment_with_no_precedent(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    night = datetime.now(timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"), created_at=night)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("10")


def test_unusual_time_does_not_flag_when_user_has_night_precedent(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    prior_night = now.replace(hour=2, minute=0, second=0, microsecond=0) - timedelta(days=1)
    _completed_card_payment(db_session, seeded_user.id, Decimal("50.00"), created_at=prior_night)
    night = now.replace(hour=3, minute=0, second=0, microsecond=0)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"), created_at=night)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


def test_unusual_time_does_not_flag_daytime_payment(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    daytime = datetime.now(timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0)
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("50.00"), created_at=daytime)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


# ---- weighted combination: co-occurring flags score more than their plain
# sum, capped so it can't spiral — see fraud/service.py's _combine_score() ----


def test_combine_score_applies_documented_multiplier_per_flag_count():
    from app.fraud.service import _combine_score

    def flags(count):
        return [(FraudFlagCode.NEW_DEVICE, Decimal("10"), "x") for _ in range(count)]

    assert _combine_score([]) == Decimal("0")
    assert _combine_score(flags(1)) == Decimal("10.00")  # 10 * 1.00
    assert _combine_score(flags(2)) == Decimal("23.00")  # 20 * 1.15
    assert _combine_score(flags(3)) == Decimal("39.00")  # 30 * 1.30
    assert _combine_score(flags(4)) == Decimal("56.00")  # 40 * 1.40
    assert _combine_score(flags(5)) == Decimal("70.00")  # 50 * 1.40 (bonus capped, not 1.55)


# ---- get_recent_activity(): extracted, independently-callable read ----


def test_get_recent_activity_returns_only_transactions_within_window(db_session, seeded_user):
    now = datetime.now(timezone.utc)
    _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"), created_at=now - timedelta(minutes=2))
    _completed_card_payment(db_session, seeded_user.id, Decimal("20.00"), created_at=now - timedelta(hours=2))

    recent = FraudService(db_session).get_recent_activity(seeded_user.id, window=timedelta(minutes=10), as_of=now)

    assert len(recent) == 1
    assert recent[0].amount == Decimal("10.00")


def test_get_recent_activity_defaults_to_last_24_hours_from_now(db_session, seeded_user):
    now = datetime.now(timezone.utc)
    _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"), created_at=now - timedelta(hours=1))
    _completed_card_payment(db_session, seeded_user.id, Decimal("20.00"), created_at=now - timedelta(days=2))

    recent = FraudService(db_session).get_recent_activity(seeded_user.id)

    assert len(recent) == 1
    assert recent[0].amount == Decimal("10.00")


# ---- get_user_spending_profile(): extracted, independently-callable read ----


def test_get_user_spending_profile_computes_average_and_history_count(db_session, seeded_user):
    for amount in (Decimal("50.00"), Decimal("100.00"), Decimal("150.00")):
        _completed_card_payment(db_session, seeded_user.id, amount)

    profile = FraudService(db_session).get_user_spending_profile(seeded_user.id)

    assert profile.card_payment_history_count == 3
    assert profile.by_currency["RON"].average_card_payment_amount == Decimal("100.00")
    assert profile.by_currency["RON"].card_payment_history_count == 3
    assert profile.spending_by_type is not None


def test_get_user_spending_profile_average_is_none_without_history(db_session, seeded_user):
    profile = FraudService(db_session).get_user_spending_profile(seeded_user.id)

    assert profile.card_payment_history_count == 0
    assert profile.by_currency == {}


def test_get_user_spending_profile_breaks_down_by_currency_not_a_blended_average(db_session, seeded_user):
    """FIX 1: multi-currency history is reported per currency, never as one
    blended average that would be meaningless across currencies."""
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("100.00"), currency="RON")
    for _ in range(2):
        _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"), currency="USD")

    profile = FraudService(db_session).get_user_spending_profile(seeded_user.id)

    assert profile.card_payment_history_count == 5
    assert set(profile.by_currency) == {"RON", "USD"}
    assert profile.by_currency["RON"].average_card_payment_amount == Decimal("100.00")
    assert profile.by_currency["RON"].card_payment_history_count == 3
    assert profile.by_currency["USD"].average_card_payment_amount == Decimal("10.00")
    assert profile.by_currency["USD"].card_payment_history_count == 2


# ---- get_known_devices(): extracted, independently-callable read ----


def test_get_known_devices_orders_most_recently_active_first(db_session, seeded_user):
    now = datetime.now(timezone.utc)
    older = _device(db_session, seeded_user.id, trusted=True, device_name="Laptop", active_at=now - timedelta(days=5))
    newer = _device(db_session, seeded_user.id, trusted=False, device_name="Phone", active_at=now)

    devices = FraudService(db_session).get_known_devices(seeded_user.id)

    assert [d.id for d in devices] == [newer.id, older.id]


# ---- POST /fraud/cases/{id}/investigate: admin-only, delegates to
# ai/fraud/agent.py (mocked here — never a live Azure call), persists the
# result onto FraudCase.agent_analysis ----


def test_investigate_endpoint_rejects_non_admin(client, db_session, seeded_user):
    _transaction, _wallet, _card, case = _create_blocked_payment(db_session, seeded_user)

    login = client.post("/api/v1/auth/login", json={"email": "fraud-user@example.com", "password": "Sup3rSecret!"})
    token = login.json()["tokens"]["access_token"]

    response = client.post(f"/api/v1/fraud/cases/{case.id}/investigate", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_investigate_endpoint_admin_triggers_agent_and_persists_analysis(client, db_session, seeded_user, monkeypatch):
    from app.ai.fraud import agent as fraud_agent_module

    _transaction, _wallet, _card, case = _create_blocked_payment(db_session, seeded_user)
    admin = _admin(db_session)
    admin.role = UserRole.ADMIN

    def _fake_investigate(case_id, db):
        return fraud_agent_module.InvestigationResult(
            risk_level=FraudRiskLevel.HIGH,
            explanation="Elevated risk: new device combined with a high-value payment.",
            summary="Elevated risk.",
            case_overview={"deterministic_risk_score": Decimal("74.75")},
            suspicious_signals=["NEW_DEVICE: Payment from an untrusted device"],
            recommended_checks=["Confirm whether the latest active device belongs to the customer."],
        )

    monkeypatch.setattr(fraud_agent_module, "investigate", _fake_investigate)

    login = client.post("/api/v1/auth/login", json={"email": "fraud-admin@example.com", "password": "Sup3rSecret!"})
    token = login.json()["tokens"]["access_token"]

    response = client.post(f"/api/v1/fraud/cases/{case.id}/investigate", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["agent_analysis"]["risk_level"] == "HIGH"
    assert "elevated risk" in body["agent_analysis"]["explanation"].lower()
    assert body["agent_analysis"]["summary"] == "Elevated risk."
    assert body["agent_analysis"]["case_overview"]["deterministic_risk_score"] == "74.75"
    assert body["agent_analysis"]["suspicious_signals"] == ["NEW_DEVICE: Payment from an untrusted device"]
    assert body["agent_analysis"]["recommended_checks"] == [
        "Confirm whether the latest active device belongs to the customer."
    ]
    # risk_score/status are untouched by the agent — still the deterministic values.
    assert Decimal(body["risk_score"]) == case.risk_score
    assert body["status"] == "PENDING_REVIEW"

    db_session.refresh(case)
    assert case.agent_analysis is not None


def test_get_case_endpoint_returns_cached_agent_analysis_without_rerunning_agent(
    client, db_session, seeded_user, monkeypatch
):
    from app.ai.fraud import agent as fraud_agent_module

    _transaction, _wallet, _card, case = _create_blocked_payment(db_session, seeded_user)
    admin = _admin(db_session)
    admin.role = UserRole.ADMIN
    FraudService(db_session).save_agent_analysis(case, FraudRiskLevel.LOW, "Consistent with this user's prior activity.")

    def _fail_if_called(case_id, db):
        raise AssertionError("investigate() must not be called by GET /cases/{id}")

    monkeypatch.setattr(fraud_agent_module, "investigate", _fail_if_called)

    login = client.post("/api/v1/auth/login", json={"email": "fraud-admin@example.com", "password": "Sup3rSecret!"})
    token = login.json()["tokens"]["access_token"]

    response = client.get(f"/api/v1/fraud/cases/{case.id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["agent_analysis"]["risk_level"] == "LOW"
    assert body["agent_analysis"]["explanation"] == "Consistent with this user's prior activity."
