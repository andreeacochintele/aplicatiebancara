import uuid
from decimal import Decimal

import pytest

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.credit import agent, tools
from app.ai.tools.base import ToolContext
from app.core.exceptions import ValidationError
from app.credit.models import LoanProductType
from app.credit.schemas import CreditApplicationCreate, CreditScorePublic
from app.credit.service import CreditService
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="credit-agent-user@example.com", password="Sup3rSecret!", first_name="Credit", last_name="Agent")
    )


@pytest.fixture()
def seeded_loan(db_session, seeded_user):
    """A real, fully server-computed personal loan + installment schedule,
    via the same application -> auto-approve -> create_loan flow the
    product uses (not hand-built rows) — so simulate_early_repayment()'s
    exact fields (Loan.monthly_payment, installment interest_amount) are
    genuinely Dev3's own numbers, not test fixtures pretending to be."""
    service = CreditService(db_session)
    application = service.create_application(
        seeded_user.id,
        CreditApplicationCreate(
            type="PERSONAL_LOAN",
            loan_product_type=LoanProductType.PERSONAL_LOAN,
            requested_amount=Decimal("6000"),
            currency="RON",
            requested_term_months=12,
        ),
    )
    return service.create_loan_from_application(seeded_user.id, application.id)


# ---- _select_tool: keyword dispatch (pure function, no DB/LLM) ----


@pytest.mark.parametrize(
    "message, expected_tool",
    [
        ("Can I pay off my loan early with an extra 500 RON?", "early_repayment"),
        ("What's my monthly payment / installment?", "monthly_payment"),
        ("How much do I still owe, what's outstanding?", "remaining_principal"),
        ("Tell me about my loans", "loan_details"),
        ("What's my credit score?", "credit_score"),
    ],
)
def test_select_tool_matches_expected_keyword(message, expected_tool):
    assert agent._select_tool(message) == expected_tool


def test_select_tool_falls_back_to_credit_score_by_default():
    assert agent._select_tool("hello there, banking assistant") == "credit_score"


# ---- tools.py: proves each tool reuses CreditService, not a reimplementation ----


def test_get_credit_score_reuses_credit_service(db_session, seeded_user):
    result = tools.get_credit_score(ToolContext(user_id=seeded_user.id, db=db_session))
    assert isinstance(result, CreditScorePublic)
    assert result.score == CreditService(db_session).get_score(seeded_user.id).score


def test_get_loan_details_reuses_credit_service(db_session, seeded_user, seeded_loan):
    result = tools.get_loan_details(ToolContext(user_id=seeded_user.id, db=db_session))
    assert len(result) == 1
    assert result[0].id == seeded_loan.id
    assert result[0].principal_amount == seeded_loan.principal_amount


def test_calculate_monthly_payment_and_remaining_principal_use_the_same_active_loan(db_session, seeded_user, seeded_loan):
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)
    payment = tools.calculate_monthly_payment(ctx)
    principal = tools.get_remaining_principal(ctx)

    assert len(payment) == 1
    assert payment[0].monthly_payment == seeded_loan.monthly_payment
    assert len(principal) == 1
    assert principal[0].outstanding_principal == seeded_loan.outstanding_principal


def test_extract_amount_picks_the_largest_number_in_the_message():
    assert tools.extract_amount("I have 2 loans, can I pay an extra 1000 RON?") == Decimal("1000")
    assert tools.extract_amount("no numbers here") is None


def test_simulate_early_repayment_returns_none_without_an_active_loan(db_session, seeded_user):
    result = tools.simulate_early_repayment(ToolContext(user_id=seeded_user.id, db=db_session), Decimal("100"))
    assert result is None


def test_simulate_early_repayment_rejects_non_positive_amounts(db_session, seeded_user, seeded_loan):
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)
    with pytest.raises(ValidationError):
        tools.simulate_early_repayment(ctx, Decimal("0"))
    with pytest.raises(ValidationError):
        tools.simulate_early_repayment(ctx, Decimal("-50"))


def test_simulate_early_repayment_partial_payment_is_approximate_and_reduces_payment_and_interest(
    db_session, seeded_user, seeded_loan
):
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)
    result = tools.simulate_early_repayment(ctx, Decimal("500"))

    assert result is not None
    assert result.is_approximate is True
    assert result.outstanding_principal_before == seeded_loan.outstanding_principal
    assert result.principal_after_extra_payment == seeded_loan.outstanding_principal - Decimal("500")
    assert result.current_monthly_payment == seeded_loan.monthly_payment
    # A smaller principal amortized over the same term/rate must cost less.
    assert result.new_monthly_payment < result.current_monthly_payment
    assert result.interest_saved is not None and result.interest_saved > 0


def test_simulate_early_repayment_full_payoff_is_exact(db_session, seeded_user, seeded_loan):
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)
    huge_payment = seeded_loan.outstanding_principal + Decimal("1000")

    result = tools.simulate_early_repayment(ctx, huge_payment)

    assert result is not None
    assert result.is_approximate is False
    assert result.principal_after_extra_payment == Decimal("0")
    assert result.new_monthly_payment is None
    assert result.interest_saved == result.current_remaining_interest


# ---- agent.py: mocked at the tool-call/LLM boundary, never a live Azure call ----


def test_handle_combines_llm_explanation_with_exact_deterministic_figures(db_session, seeded_user, seeded_loan, monkeypatch):
    monkeypatch.setattr(agent, "_explain", lambda message, data_summary: "Mocked explanation.")

    reply = agent.handle("what's my remaining principal?", seeded_user.id, db_session)

    assert reply.startswith("Mocked explanation.\n\n")
    assert str(seeded_loan.outstanding_principal) in reply
    assert seeded_loan.currency in reply


def test_handle_asks_for_an_amount_without_calling_the_llm_when_none_is_given(db_session, seeded_user, seeded_loan, monkeypatch):
    def _fail_if_called(message, data_summary):
        raise AssertionError("_explain must not be called before an amount is known")

    monkeypatch.setattr(agent, "_explain", _fail_if_called)

    reply = agent.handle("can I pay off my loan early?", seeded_user.id, db_session)

    assert reply == agent._NO_AMOUNT_REPLY


def test_handle_simulates_early_repayment_when_an_amount_is_given(db_session, seeded_user, seeded_loan, monkeypatch):
    monkeypatch.setattr(agent, "_explain", lambda message, data_summary: "Mocked explanation.")

    reply = agent.handle("can I pay off my loan early with an extra 500 RON?", seeded_user.id, db_session)

    assert reply.startswith("Mocked explanation.\n\n")
    assert "approximate" in reply.lower()
    assert "500" in reply


def test_handle_propagates_azure_not_configured_from_explain(db_session, seeded_user, seeded_loan, monkeypatch):
    def _raise_not_configured(message, data_summary):
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    monkeypatch.setattr(agent, "_explain", _raise_not_configured)

    with pytest.raises(AzureFoundryNotConfiguredError):
        agent.handle("what's my credit score?", seeded_user.id, db_session)
