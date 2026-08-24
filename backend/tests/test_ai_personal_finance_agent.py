import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.personal_finance import agent, tools
from app.ai.tools.base import ToolContext, ToolDataUnavailableError
from app.analytics.schemas import ForecastResponse
from app.budgets.schemas import BudgetCreate
from app.budgets.service import BudgetService
from app.merchants.schemas import CashbackOfferCreate, MerchantCreate
from app.merchants.service import MerchantService
from app.savings.schemas import SavingsGoalCreate
from app.savings.service import SavingsService
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="pf-agent-user@example.com", password="Sup3rSecret!", first_name="PF", last_name="Agent")
    )


# ---- _select_tool: keyword dispatch (pure function, no DB/LLM) ----


@pytest.mark.parametrize(
    "message, expected_tool",
    [
        ("What's my budget status?", "budgets"),
        ("How close am I to my savings goal?", "savings_goals"),
        ("Any cashback offers right now?", "cashback_offers"),
        ("Can you forecast my end of month balance?", "forecast"),
        ("What's my monthly income?", "income"),
        ("Do I have any recurring subscriptions?", "recurring"),
        ("How much did I spend this month?", "spending_by_type"),
        ("Show me my transaction history", "transactions"),
        ("What's my wallet balance?", "wallet_balances"),
    ],
)
def test_select_tool_matches_expected_keyword(message, expected_tool):
    assert agent._select_tool(message) == expected_tool


def test_select_tool_falls_back_to_wallet_balances_by_default():
    assert agent._select_tool("hello there, banking assistant") == "wallet_balances"


# ---- tools.py: proves each tool reuses the real service layer, not a reimplementation ----


def test_get_wallet_balances_reuses_wallets_service(db_session, seeded_user):
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    wallet.available_balance = Decimal("1234.56")
    db_session.flush()

    result = tools.get_wallet_balances(ToolContext(user_id=seeded_user.id, db=db_session))

    assert len(result) == 1
    assert result[0].currency == "RON"
    assert result[0].available_balance == Decimal("1234.56")
    assert result[0].is_main is True


def test_get_budgets_reuses_budgets_service(db_session, seeded_user):
    BudgetService(db_session).create_budget(
        seeded_user.id, BudgetCreate(name="Groceries", limit_amount=Decimal("500"), currency="RON")
    )

    result = tools.get_budgets(ToolContext(user_id=seeded_user.id, db=db_session))

    assert len(result) == 1
    assert result[0].name == "Groceries"
    assert result[0].limit_amount == Decimal("500")


def test_get_savings_goals_reuses_savings_service(db_session, seeded_user):
    SavingsService(db_session).create_goal(
        seeded_user.id, SavingsGoalCreate(name="Vacation", target_amount=Decimal("2000"), currency="RON")
    )

    result = tools.get_savings_goals(ToolContext(user_id=seeded_user.id, db=db_session))

    assert len(result) == 1
    assert result[0].name == "Vacation"
    assert result[0].target_amount == Decimal("2000")


def test_get_cashback_offers_filters_to_merchants_with_an_active_offer(db_session):
    merchants_service = MerchantService(db_session)
    with_offer = merchants_service.create_merchant(MerchantCreate(name="CoffeeCo", category="Food"))
    merchants_service.create_merchant(MerchantCreate(name="NoOfferCo", category="Retail"))
    today = datetime.now(timezone.utc).date()
    merchants_service.create_cashback_offer(
        with_offer.id,
        CashbackOfferCreate(
            cashback_percent=Decimal("5"),
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=30),
        ),
    )

    result = tools.get_cashback_offers(ToolContext(user_id=uuid.uuid4(), db=db_session))

    assert [m.name for m in result] == ["CoffeeCo"]
    assert result[0].active_offer.cashback_percent == Decimal("5")


def test_get_transactions_and_spending_by_category_reuse_real_data(db_session, seeded_user):
    db_session.add(
        Transaction(
            initiator_user_id=seeded_user.id,
            type=TransactionType.CARD_PAYMENT,
            status=TransactionStatus.COMPLETED,
            amount=Decimal("42.50"),
            currency="RON",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)

    transactions = tools.get_transactions(ctx)
    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("42.50")
    assert transactions[0].type == TransactionType.CARD_PAYMENT

    spending = tools.get_spending_by_category(ctx)
    assert len(spending.items) == 1
    assert spending.items[0].type == TransactionType.CARD_PAYMENT
    assert spending.items[0].total_amount == Decimal("42.50")


def test_forecast_month_end_balance_reuses_analytics_service_as_is(db_session, seeded_user):
    WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))

    result = tools.forecast_month_end_balance(ToolContext(user_id=seeded_user.id, db=db_session))

    assert isinstance(result, ForecastResponse)
    assert result.currency == "RON"
    assert result.note  # analytics/service.py's own "simplified" disclaimer, not rewritten here


def test_get_monthly_income_raises_tool_data_unavailable_instead_of_a_guess(db_session):
    with pytest.raises(ToolDataUnavailableError):
        tools.get_monthly_income(ToolContext(user_id=uuid.uuid4(), db=db_session))


def test_get_recurring_payments_raises_tool_data_unavailable_instead_of_a_guess(db_session):
    with pytest.raises(ToolDataUnavailableError):
        tools.get_recurring_payments(ToolContext(user_id=uuid.uuid4(), db=db_session))


# ---- agent.py: mocked at the tool-call/LLM boundary, never a live Azure call ----


def test_handle_combines_llm_explanation_with_exact_deterministic_figures(db_session, seeded_user, monkeypatch):
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    wallet.available_balance = Decimal("777.10")
    db_session.flush()
    monkeypatch.setattr(agent, "_explain", lambda message, data_summary, history=None: "Mocked explanation.")

    reply = agent.handle("what's my balance?", seeded_user.id, db_session)

    assert reply.startswith("Mocked explanation.\n\n")
    assert "777.10" in reply
    assert "RON" in reply


def test_handle_returns_the_unavailable_message_without_calling_the_llm(db_session, monkeypatch):
    def _fail_if_called(message, data_summary):
        raise AssertionError("_explain must not be called when tool data is unavailable")

    monkeypatch.setattr(agent, "_explain", _fail_if_called)

    reply = agent.handle("what's my monthly income?", uuid.uuid4(), db_session)

    assert reply == (
        "Monthly income isn't available yet: there's no transaction type or "
        "service aggregate for incoming funds in the backend."
    )


def test_handle_propagates_azure_not_configured_from_explain(db_session, seeded_user, monkeypatch):
    def _raise_not_configured(message, data_summary, history=None):
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    monkeypatch.setattr(agent, "_explain", _raise_not_configured)

    with pytest.raises(AzureFoundryNotConfiguredError):
        agent.handle("what's my balance?", seeded_user.id, db_session)
