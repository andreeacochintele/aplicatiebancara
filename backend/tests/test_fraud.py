import uuid
from datetime import datetime, timedelta, timezone
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
from app.merchants.schemas import MerchantCreate
from app.merchants.service import MerchantService
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


def _completed_card_payment(db_session, user_id, amount, merchant_id=None, created_at=None):
    transaction = Transaction(
        initiator_user_id=user_id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=amount,
        currency="RON",
        merchant_id=merchant_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction


def _pending_transaction(user_id, wallet_id, amount, merchant_id=None, created_at=None):
    return Transaction(
        id=uuid.uuid4(),
        initiator_user_id=user_id,
        source_wallet_id=wallet_id,
        merchant_id=merchant_id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.PROCESSING,
        amount=amount,
        currency="RON",
        created_at=created_at or datetime.now(timezone.utc),
    )


def _create_blocked_payment(db_session, seeded_user, amount=Decimal("500.00"), card_type=CardType.DEBIT):
    """3x50 RON baseline + an untrusted device -> a 10x-average HIGH_AMOUNT
    (capped at 40) + NEW_DEVICE (25) = 65 base, combined with the 2-flag
    weighted-combination multiplier (x1.15) = 74.75, which crosses the
    65-point threshold."""
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
    """400 is exactly 4x the 100 average -> the minimum trigger ratio (>3x),
    so this scores the proportional flag's base points (15), not the cap."""
    wallet = _wallet(db_session, seeded_user.id)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("100.00"))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("400.00"))

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("20")


def test_high_amount_does_not_flag_without_enough_history(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    _completed_card_payment(db_session, seeded_user.id, Decimal("100.00"))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("5000.00"))

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


def test_high_velocity_flags_five_transactions_in_five_minutes(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    for _ in range(4):
        _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"), created_at=now - timedelta(minutes=1))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("10.00"), created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("15")


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

    assert decision.score == Decimal("20")


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
    # so 20 base + 6*2 = 32 (still under the 40 cap).
    assert decision.score == Decimal("32")


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
    # trigger (base 20 points). velocity = the 4 unrelated transactions (2
    # matching ones excluded) + this one = 5 -> HIGH_VELOCITY at its minimum
    # trigger too (base 15 points) - still fires on the genuinely separate
    # activity. Two flags co-occurring: (20 + 15) * 1.15 = 40.25.
    assert decision.score == Decimal("40.25")


def test_transactions_with_no_merchant_never_match_each_other_for_abuse_pattern(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    now = datetime.now(timezone.utc)
    for _ in range(2):
        _completed_card_payment(db_session, seeded_user.id, Decimal("25.00"), created_at=now - timedelta(minutes=2))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("25.00"), created_at=now)

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("0")


def test_create_card_payment_holds_funds_when_score_crosses_threshold(db_session, seeded_user):
    transaction, wallet, _card, case = _create_blocked_payment(db_session, seeded_user)

    assert transaction.status == TransactionStatus.PENDING_REVIEW
    assert transaction.fraud_score == Decimal("74.75")
    assert wallet.available_balance == Decimal("500.00")
    assert wallet.reserved_balance == Decimal("500.00")

    ledger_types = [entry.entry_type.value for entry in transaction.ledger_entries]
    assert ledger_types == ["HOLD"]

    assert case.status == FraudCaseStatus.PENDING_REVIEW
    assert case.risk_score == Decimal("74.75")
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

    assert score_at_minimum == Decimal("20")  # 15 base + 5*1
    assert score_further_over == Decimal("30")  # 15 base + 5*3
    assert score_further_over > score_at_minimum


def test_high_amount_points_cap_at_max_for_extreme_outliers(db_session, seeded_user):
    wallet = _wallet(db_session, seeded_user.id)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("10.00"))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("5000.00"))  # 500x average

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("40")  # capped, not 15 + 5*497


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
    assert profile.average_card_payment_amount == Decimal("100.00")
    assert profile.spending_by_type is not None


def test_get_user_spending_profile_average_is_none_without_history(db_session, seeded_user):
    profile = FraudService(db_session).get_user_spending_profile(seeded_user.id)

    assert profile.card_payment_history_count == 0
    assert profile.average_card_payment_amount is None


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
            risk_level=FraudRiskLevel.HIGH, explanation="Elevated risk: new device combined with a high-value payment."
        )

    monkeypatch.setattr(fraud_agent_module, "investigate", _fake_investigate)

    login = client.post("/api/v1/auth/login", json={"email": "fraud-admin@example.com", "password": "Sup3rSecret!"})
    token = login.json()["tokens"]["access_token"]

    response = client.post(f"/api/v1/fraud/cases/{case.id}/investigate", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["agent_analysis"]["risk_level"] == "HIGH"
    assert "elevated risk" in body["agent_analysis"]["explanation"].lower()
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
