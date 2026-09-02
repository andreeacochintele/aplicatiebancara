import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ai.actions.schemas import AgentResult
from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.guardrails import INJECTION_GUARDRAILS, RESPONSE_FORMAT_RULE
from app.ai.personal_finance import agent, tools
from app.ai.tools.base import ToolContext, ToolDataUnavailableError
from app.analytics.schemas import ForecastResponse
from app.budgets.schemas import BudgetCreate
from app.budgets.service import BudgetService
from app.merchants.schemas import CashbackOfferCreate, MerchantCreate
from app.merchants.service import MerchantService
from app.savings.schemas import SavingsGoalCreate
from app.savings.service import SavingsService
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
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
        ("Can I get an account statement?", "statement"),
        ("What's my budget status?", "budgets"),
        ("How close am I to my savings goal?", "savings_goals"),
        ("Any cashback offers right now?", "cashback_offers"),
        ("Can you forecast my end of month balance?", "forecast"),
        ("What's my monthly income?", "income"),
        ("Do I have any recurring subscriptions?", "recurring"),
        ("How much did I spend this month?", "spending_by_type"),
        ("Show me my transaction history", "transactions"),
        ("What's my net worth?", "net_worth"),
        ("What's my total balance across all my accounts?", "net_worth"),
        ("What's my wallet balance?", "wallet_balances"),
    ],
)
def test_select_tool_matches_expected_keyword(message, expected_tool):
    assert agent._select_tool(message) == expected_tool


def test_select_tool_falls_back_to_wallet_balances_by_default():
    assert agent._select_tool("hello there, banking assistant") == "wallet_balances"


@pytest.mark.parametrize(
    "message, expected_tool",
    [
        ("Vreau un extras de cont", "statement"),
        ("Care e bugetul meu?", "budgets"),
        ("Cat am economisit pentru obiectivul meu?", "savings_goals"),
        ("Am vreo reducere de cashback acum?", "cashback_offers"),
        ("Poti sa faci o prognoza pentru finalul lunii?", "forecast"),
        ("Care e venitul meu lunar?", "income"),
        ("Am vreun abonament recurent?", "recurring"),
        ("Cat am cheltuit luna asta?", "spending_by_type"),
        ("Arata-mi istoricul tranzactiilor", "transactions"),
        ("Cat am in toate conturile?", "net_worth"),
        ("Ce sold am?", "wallet_balances"),
    ],
)
def test_select_tool_matches_expected_keyword_in_romanian(message, expected_tool):
    assert agent._select_tool(message) == expected_tool


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


def test_get_wallet_balances_excludes_closed_wallets(db_session, seeded_user):
    WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    pln = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="PLN"))
    WalletService(db_session).close_wallet(seeded_user.id, pln.id)

    result = tools.get_wallet_balances(ToolContext(user_id=seeded_user.id, db=db_session))

    assert [w.currency for w in result] == ["RON"]


def test_get_net_worth_reuses_analytics_service_real_fx_conversion(db_session, seeded_user):
    ron = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    ron.available_balance = Decimal("100.00")
    eur = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    eur.available_balance = Decimal("10.00")
    eur.reserved_balance = Decimal("5.00")
    db_session.flush()

    result = tools.get_net_worth(ToolContext(user_id=seeded_user.id, db=db_session))

    assert result.base_currency == "RON"
    # Real FXService conversion, not hand-computed here — just prove the
    # reserved EUR amount was never added into the total.
    from app.fx.service import FXService

    expected_eur_converted = (eur.available_balance * FXService(db_session).get_rate("EUR", "RON")).quantize(Decimal("0.01"))
    assert result.total_available_balance == Decimal("100.00") + expected_eur_converted


# ---- correctness/hallucination fix: the agent must never claim it computed
# a converted total unless it actually called get_net_worth() and got one —
# see _net_worth()'s formatting and the system prompt's "never claim you
# calculated" rule.


def test_net_worth_summary_states_a_real_converted_total_and_excludes_reserved(db_session, seeded_user):
    ron = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    ron.available_balance = Decimal("100.00")
    eur = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    eur.available_balance = Decimal("10.00")
    eur.reserved_balance = Decimal("5.00")
    db_session.flush()

    summary = agent._net_worth(ToolContext(user_id=seeded_user.id, db=db_session))

    assert "Total balance across all wallets" in summary
    assert "reserved amounts excluded" in summary
    assert "RON" in summary and "EUR" in summary
    assert "5.00" in summary  # the reserved EUR amount is shown, but noted as excluded
    assert "not included in the total" in summary


def test_system_prompt_forbids_claiming_a_calculation_that_wasnt_actually_run():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "never claim you calculated, converted, totaled" in lowered


# ---- shared ai/knowledge/app_overview.md + ai/guardrails.py: same static
# knowledge and guardrails the Support Agent uses, kept clearly separate
# from the "never state a number from the (per-request) data below" rule ----


def test_system_prompt_includes_the_shared_app_overview_verbatim():
    assert agent._APP_OVERVIEW in agent._SYSTEM_PROMPT


def test_system_prompt_includes_the_shared_injection_and_format_guardrails():
    assert INJECTION_GUARDRAILS in agent._SYSTEM_PROMPT
    assert RESPONSE_FORMAT_RULE in agent._SYSTEM_PROMPT


def test_system_prompt_scopes_the_never_state_a_number_rule_to_the_data_block_only():
    # The app overview legitimately contains numbers (e.g. a tier's points
    # multiplier) — the "never state a number" rule must read as applying
    # only to the per-request data block, not to this general reference
    # text, or the model would be told to contradict itself.
    assert any(char.isdigit() for char in agent._APP_OVERVIEW)
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "never state a number from the data below" in lowered or "the data below" in lowered
    assert "applies only to that per-request block" in lowered


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


def _card_payment_with_ledger_entry(db_session, user_id, wallet, amount, description):
    transaction = Transaction(
        initiator_user_id=user_id,
        source_wallet_id=wallet.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=amount,
        currency=wallet.currency,
        description=description,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()
    db_session.add(
        WalletLedgerEntry(
            wallet_id=wallet.id,
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=amount,
            currency=wallet.currency,
            balance_after=wallet.available_balance - amount,
        )
    )
    db_session.flush()
    return transaction


def test_get_account_statement_reuses_statement_service(db_session, seeded_user):
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    wallet.available_balance = Decimal("500.00")
    db_session.flush()
    _card_payment_with_ledger_entry(db_session, seeded_user.id, wallet, Decimal("42.50"), "Coffee")

    result = tools.get_account_statement(ToolContext(user_id=seeded_user.id, db=db_session))

    assert result.wallet_id == wallet.id
    assert result.currency == "RON"


def test_get_account_statement_raises_tool_data_unavailable_without_a_main_wallet(db_session, seeded_user):
    with pytest.raises(ToolDataUnavailableError):
        tools.get_account_statement(ToolContext(user_id=seeded_user.id, db=db_session))


# ---- wallet selection: live-observed always returning the main wallet's
# statement regardless of which currency the user actually asked for
# ("arata-mi extrasul cont RON" showed USD because USD was main) ----


def test_get_account_statement_uses_the_wallet_matching_the_message_currency(db_session, seeded_user):
    wallets = WalletService(db_session)
    usd_wallet = wallets.create_wallet(seeded_user.id, WalletCreate(currency="USD", is_main=True))
    ron_wallet = wallets.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    db_session.flush()

    result = tools.get_account_statement(
        ToolContext(user_id=seeded_user.id, db=db_session), "Arata-mi extrasul cont RON"
    )

    assert result.wallet_id == ron_wallet.id
    assert result.currency == "RON"
    assert result.wallet_id != usd_wallet.id


def test_get_account_statement_falls_back_to_main_when_no_currency_is_named(db_session, seeded_user):
    wallets = WalletService(db_session)
    usd_wallet = wallets.create_wallet(seeded_user.id, WalletCreate(currency="USD", is_main=True))
    wallets.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    db_session.flush()

    result = tools.get_account_statement(ToolContext(user_id=seeded_user.id, db=db_session), "Vreau un extras de cont")

    assert result.wallet_id == usd_wallet.id


def test_get_account_statement_ignores_a_currency_the_user_does_not_hold(db_session, seeded_user):
    usd_wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="USD", is_main=True))
    db_session.flush()

    result = tools.get_account_statement(ToolContext(user_id=seeded_user.id, db=db_session), "extrasul cont EUR")

    assert result.wallet_id == usd_wallet.id


def test_statement_summary_includes_balances_and_a_transaction(db_session, seeded_user):
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    wallet.available_balance = Decimal("500.00")
    db_session.flush()
    _card_payment_with_ledger_entry(db_session, seeded_user.id, wallet, Decimal("42.50"), "Coffee")

    statement = tools.get_account_statement(ToolContext(user_id=seeded_user.id, db=db_session))
    summary = agent._format_statement_summary(statement)

    assert "Account statement" in summary
    assert "Opening balance" in summary
    assert "Closing balance" in summary
    assert "Coffee" in summary


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


def test_handle_returns_a_download_attachment_for_a_statement_request(db_session, seeded_user, monkeypatch):
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    wallet.available_balance = Decimal("500.00")
    db_session.flush()
    _card_payment_with_ledger_entry(db_session, seeded_user.id, wallet, Decimal("42.50"), "Coffee")
    monkeypatch.setattr(agent, "_explain", lambda message, data_summary, history=None: "Mocked explanation.")

    result = agent.handle("can I get my account statement?", seeded_user.id, db_session)

    assert isinstance(result, AgentResult)
    assert result.reply.startswith("Mocked explanation.\n\n")
    assert "Account statement" in result.reply
    assert result.action_card is None
    assert result.download is not None
    assert result.download.url.startswith("/statements/export?")
    assert f"wallet_id={wallet.id}" in result.download.url
    assert "format=pdf" in result.download.url


def test_handle_returns_the_unavailable_message_for_a_statement_request_with_no_main_wallet(db_session, monkeypatch):
    def _fail_if_called(message, data_summary, history=None):
        raise AssertionError("_explain must not be called when tool data is unavailable")

    monkeypatch.setattr(agent, "_explain", _fail_if_called)

    reply = agent.handle("can I get my account statement?", uuid.uuid4(), db_session)

    assert reply == "No main wallet to generate a statement for."


def test_handle_propagates_azure_not_configured_from_explain(db_session, seeded_user, monkeypatch):
    def _raise_not_configured(message, data_summary, history=None):
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON", is_main=True))
    monkeypatch.setattr(agent, "_explain", _raise_not_configured)

    with pytest.raises(AzureFoundryNotConfiguredError):
        agent.handle("what's my balance?", seeded_user.id, db_session)


# ---- proactive-answering fix: a clearly-scoped question calls its tool in the
# same turn (dispatch is deterministic Python — see agent.py's module
# docstring), and the system prompt tells the LLM to answer confidently
# with that data rather than ask for confirmation first. Whether a real
# model actually stops hedging can't be asserted from a mocked test — that's
# what the live smoke test in the task report covers; these tests protect
# the fix itself from being silently removed and confirm the dispatch these
# examples rely on.


def test_select_tool_dispatches_a_clearly_scoped_spending_question_to_spending_by_type():
    assert agent._select_tool("how much did I spend on groceries this month") == "spending_by_type"


def test_system_prompt_instructs_answering_directly_without_asking_for_confirmation():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "do not ask for confirmation first" in lowered
    assert "treat it as answered" in lowered


def test_system_prompt_still_allows_clarifying_questions_when_genuinely_ambiguous():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "genuinely ambiguous" in lowered


def test_system_prompt_instructs_matching_the_users_language_defaulting_to_romanian():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "same language the user's message is written in" in lowered
    assert "default to romanian" in lowered


# ---- no-duplicate-dump fix: the deterministic data block is still shown to
# the user verbatim after the reply (so a figure can never be silently
# recalculated), but the LLM must not restate it as a second list itself.


def test_system_prompt_instructs_not_repeating_the_data_as_a_second_list():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "must never contain any number" in lowered
    assert "never quote, copy, or closely" in lowered


def test_append_summary_skips_the_append_when_the_llm_already_quoted_it_verbatim():
    summary = "Wallet balances:\n- RON 0.0 available — main wallet"
    explanation = f"You don't have any funds right now.\n\n{summary}"

    assert agent._append_summary(explanation, summary) == explanation


def test_append_summary_appends_once_when_the_llm_did_not_quote_it():
    summary = "Wallet balances:\n- RON 0.0 available — main wallet"
    explanation = "You don't have any funds right now."

    assert agent._append_summary(explanation, summary) == f"{explanation}\n\n{summary}"


def test_empty_state_messages_read_as_full_sentences_not_debug_labels(db_session, seeded_user):
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)
    assert agent._wallet_balances(ctx) == "You don't have any wallets yet."
    assert agent._budgets(ctx) == "You don't have any budgets set up yet."
    assert agent._savings_goals(ctx) == "You don't have any savings goals set up yet."
