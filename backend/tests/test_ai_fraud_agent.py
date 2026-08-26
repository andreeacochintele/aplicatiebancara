import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.fraud import agent, tools
from app.auth.models import SessionStatus, UserDevice, UserSession
from app.cards.models import CardType
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.fraud.models import FraudCase
from app.fraud.schemas import FraudRiskLevel
from app.fraud.service import FraudService, SpendingProfile
from app.merchants.schemas import MerchantCreate
from app.merchants.service import MerchantService
from app.transactions.schemas import CardPaymentCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="fraud-agent-user@example.com", password="Sup3rSecret!", first_name="Fraud", last_name="Agent")
    )


def _wallet(db_session, user_id, balance=Decimal("1000.00")):
    wallet = WalletService(db_session).create_wallet(user_id, WalletCreate(currency="RON"))
    wallet.available_balance = balance
    db_session.flush()
    return wallet


def _device(db_session, user_id, *, trusted, location=None, device_name="Device", last_seen_at=None):
    device = UserDevice(
        user_id=user_id, device_name=device_name, device_type="mobile", trusted=trusted, mock_location=location
    )
    if last_seen_at is not None:
        device.last_seen_at = last_seen_at
    db_session.add(device)
    db_session.flush()
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user_id,
        device_id=device.id,
        token_hash=f"hash-{device.id}",
        last_activity_at=now,
        expires_at=now + timedelta(days=1),
        status=SessionStatus.ACTIVE,
    )
    db_session.add(session)
    db_session.flush()
    return device


def _merchant(db_session, name="Nike"):
    return MerchantService(db_session).create_merchant(MerchantCreate(name=name, category="Retail", verified=True))


def _blocked_case(db_session, seeded_user) -> FraudCase:
    """A real PENDING_REVIEW case via the normal create_card_payment flow —
    same shape as test_fraud.py's _create_blocked_payment: 3x50 baseline +
    an untrusted device -> HIGH_AMOUNT (71, capped at 70) + NEW_DEVICE (25),
    weighted-combined to 109.25, past the 65-point threshold."""
    wallet = _wallet(db_session, seeded_user.id, balance=Decimal("1000.00"))
    card = CardService(db_session).create_card(
        seeded_user.id, CardCreate(type=CardType.DEBIT, default_wallet_id=wallet.id)
    )
    merchant = _merchant(db_session)
    _device(db_session, seeded_user.id, trusted=False)

    from app.transactions.models import Transaction, TransactionStatus, TransactionType

    for _ in range(3):
        t = Transaction(
            initiator_user_id=seeded_user.id,
            type=TransactionType.CARD_PAYMENT,
            status=TransactionStatus.COMPLETED,
            amount=Decimal("50.00"),
            currency="RON",
        )
        db_session.add(t)
    db_session.flush()

    transaction = TransactionService(db_session).create_card_payment(
        seeded_user.id,
        CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("500.00"), cvv=card.mock_cvv),
    )
    return db_session.query(FraudCase).filter(FraudCase.transaction_id == transaction.id).one()


# ---- tools.py: proves each tool reuses FraudService/TransactionRepository, not a reimplementation ----


def test_get_case_reuses_fraud_service(db_session, seeded_user):
    case = _blocked_case(db_session, seeded_user)

    result = tools.get_case(db_session, case.id)

    expected = FraudService(db_session).to_detail(FraudService(db_session).get_case(case.id))
    assert result.id == expected.id
    assert result.risk_score == expected.risk_score
    assert {f.code for f in result.flags} == {f.code for f in expected.flags}


def test_get_transaction_reuses_transaction_repository(db_session, seeded_user):
    case = _blocked_case(db_session, seeded_user)

    transaction = tools.get_transaction(db_session, case.transaction_id)

    assert transaction is not None
    assert transaction.id == case.transaction_id
    assert transaction.amount == Decimal("500.00")


def test_get_transaction_returns_none_for_unknown_id(db_session):
    assert tools.get_transaction(db_session, uuid.uuid4()) is None


def test_get_user_transaction_history_returns_all_transactions(db_session, seeded_user):
    case = _blocked_case(db_session, seeded_user)

    history = tools.get_user_transaction_history(db_session, seeded_user.id)

    # 3 seeded completed history payments + the blocked one itself.
    assert len(history) == 4
    assert any(t.id == case.transaction_id for t in history)


def test_get_known_devices_orders_most_recently_active_first(db_session, seeded_user):
    older = _device(
        db_session, seeded_user.id, trusted=True, device_name="Laptop",
        last_seen_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    newer = _device(db_session, seeded_user.id, trusted=False, device_name="Phone")

    devices = tools.get_known_devices(db_session, seeded_user.id)

    assert [d.id for d in devices] == [newer.id, older.id]


def test_get_recent_activity_reuses_fraud_service(db_session, seeded_user):
    case = _blocked_case(db_session, seeded_user)

    recent = tools.get_recent_activity(db_session, seeded_user.id)

    assert any(t.id == case.transaction_id for t in recent)


def test_get_fraud_flags_returns_flags_for_case(db_session, seeded_user):
    from app.fraud.models import FraudFlagCode

    case = _blocked_case(db_session, seeded_user)

    flags = tools.get_fraud_flags(db_session, case.id)

    assert {f.code for f in flags} == {FraudFlagCode.NEW_DEVICE, FraudFlagCode.HIGH_AMOUNT}


def test_get_user_spending_profile_reuses_fraud_service(db_session, seeded_user):
    _blocked_case(db_session, seeded_user)

    profile = tools.get_user_spending_profile(db_session, seeded_user.id)

    assert isinstance(profile, SpendingProfile)
    assert profile.card_payment_history_count == 3
    assert profile.by_currency["RON"].average_card_payment_amount == Decimal("50.00")


def test_get_investigation_context_reuses_fraud_service(db_session, seeded_user):
    case = _blocked_case(db_session, seeded_user)

    context = tools.get_investigation_context(db_session, case.id)

    expected = FraudService(db_session).build_investigation_context(case.id)
    assert context["case_overview"]["transaction_id"] == expected["case_overview"]["transaction_id"]
    assert context["behavioral_analysis"]["amount_baseline"]["average_completed_card_payment"] == Decimal("50.00")


# ---- agent._format_context: deterministic, LLM-free summary assembly ----


def test_format_context_cites_specific_data_points(db_session, seeded_user):
    case_orm = _blocked_case(db_session, seeded_user)
    case = tools.get_case(db_session, case_orm.id)
    transaction = tools.get_transaction(db_session, case.transaction_id)
    history = tools.get_user_transaction_history(db_session, case.user_id)
    devices = tools.get_known_devices(db_session, case.user_id)
    recent_activity = tools.get_recent_activity(db_session, case.user_id)
    flags = tools.get_fraud_flags(db_session, case.id)
    profile = tools.get_user_spending_profile(db_session, case.user_id)

    context = agent._format_context(case, transaction, history, devices, recent_activity, flags, profile)

    assert str(case.risk_score) in context
    assert "NEW_DEVICE" in context
    assert "HIGH_AMOUNT" in context
    assert "500.00" in context
    assert "50.00" in context  # the user's average card payment
    assert "trusted=False" in context


def test_format_context_handles_no_spending_history():
    from app.analytics.schemas import SpendingByTypeResponse

    today = datetime.now(timezone.utc).date()
    profile = SpendingProfile(
        by_currency={},
        card_payment_history_count=0,
        spending_by_type=SpendingByTypeResponse(period_start=today, period_end=today, items=[]),
    )

    class _FakeCase:
        risk_score = Decimal("0")
        status = type("S", (), {"value": "PENDING_REVIEW"})()
        hold_amount = Decimal("0")

    context = agent._format_context(_FakeCase(), None, [], [], [], [], profile)

    assert "not enough history" in context
    assert "none on record" in context


def test_format_context_serializes_structured_context():
    context = agent._format_context(
        {
            "case_overview": {"deterministic_risk_score": Decimal("74.75")},
            "generated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
    )

    assert '"deterministic_risk_score": "74.75"' in context
    assert "2026-01-01T00:00:00+00:00" in context


# ---- agent._parse_reply: pure function, extracts RISK_LEVEL + explanation ----


@pytest.mark.parametrize(
    "reply, expected_level",
    [
        ("This is unusual because of X.\nRISK_LEVEL: HIGH", FraudRiskLevel.HIGH),
        ("Looks broadly normal.\nRISK_LEVEL: LOW", FraudRiskLevel.LOW),
        ("Somewhat unusual.\nrisk_level: medium", FraudRiskLevel.MEDIUM),
    ],
)
def test_parse_reply_extracts_documented_risk_level(reply, expected_level):
    result = agent._parse_reply(reply)
    assert result.risk_level == expected_level
    assert "RISK_LEVEL" not in result.explanation


def test_parse_reply_defaults_to_medium_when_line_is_missing():
    result = agent._parse_reply("Just an explanation with no risk level line.")
    assert result.risk_level == FraudRiskLevel.MEDIUM


def test_parse_reply_defaults_to_medium_when_value_is_malformed():
    result = agent._parse_reply("Some explanation.\nRISK_LEVEL: EXTREME")
    assert result.risk_level == FraudRiskLevel.MEDIUM


# ---- agent.investigate(): mocked at the LLM boundary, never a live Azure call ----


def test_investigate_calls_all_tools_and_returns_parsed_result(db_session, seeded_user, monkeypatch):
    case = _blocked_case(db_session, seeded_user)
    captured = {}

    def _fake_explain(context: str) -> str:
        captured["context"] = context
        return "Elevated risk due to a new device and a high-value payment.\nRISK_LEVEL: HIGH"

    monkeypatch.setattr(agent, "_explain", _fake_explain)

    result = agent.investigate(case.id, db_session)

    assert result.risk_level == FraudRiskLevel.HIGH
    assert "elevated risk" in result.explanation.lower()
    assert str(case.risk_score) in captured["context"]
    assert result.case_overview["deterministic_risk_score"] == Decimal("109.25")
    assert result.summary == "Elevated risk due to a new device and a high-value payment."
    assert result.suspicious_signals


def test_investigate_propagates_azure_not_configured(db_session, seeded_user, monkeypatch):
    case = _blocked_case(db_session, seeded_user)

    def _raise_not_configured(context: str) -> str:
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    monkeypatch.setattr(agent, "_explain", _raise_not_configured)

    with pytest.raises(AzureFoundryNotConfiguredError):
        agent.investigate(case.id, db_session)
