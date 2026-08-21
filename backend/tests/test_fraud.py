import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.auth.models import SessionStatus, UserDevice, UserSession
from app.cards.models import CardStatus, CardType
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import ConflictError
from app.fraud.models import FraudCase, FraudCaseStatus, FraudFlagCode
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
    """3x50 RON baseline + an untrusted device -> HIGH_AMOUNT (30) + NEW_DEVICE
    (25) = 55, which crosses the 50-point threshold."""
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
    wallet = _wallet(db_session, seeded_user.id)
    for _ in range(3):
        _completed_card_payment(db_session, seeded_user.id, Decimal("100.00"))
    transaction = _pending_transaction(seeded_user.id, wallet.id, Decimal("400.00"))

    decision = FraudService(db_session).evaluate_transaction(transaction, wallet)

    assert decision.score == Decimal("30")


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

    assert decision.score == Decimal("25")


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
    assert transaction.fraud_score == Decimal("55")
    assert wallet.available_balance == Decimal("500.00")
    assert wallet.reserved_balance == Decimal("500.00")

    ledger_types = [entry.entry_type.value for entry in transaction.ledger_entries]
    assert ledger_types == ["HOLD"]

    assert case.status == FraudCaseStatus.PENDING_REVIEW
    assert case.risk_score == Decimal("55")
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
