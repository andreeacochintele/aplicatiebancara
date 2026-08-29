import uuid
from decimal import Decimal

import pytest

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.credit import agent, tools
from app.ai.tools.base import ToolContext
from app.core.exceptions import ValidationError
from app.credit.models import CreditApplicationStatus, LoanProductType
from app.credit.schemas import CreditApplicationCreate, CreditApplicationDecision, CreditScorePublic
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
    via the same application -> admin approve -> create_loan flow the
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
    service.decide_application(
        admin_id=seeded_user.id,
        application_id=application.id,
        data=CreditApplicationDecision(
            status=CreditApplicationStatus.APPROVED,
            offered_amount=application.requested_amount,
            offered_interest_rate=Decimal("9.90"),
        ),
    )
    loan = service.repository.get_loan_by_application(application.id)
    assert loan is not None
    return loan


# ---- _select_tool: keyword dispatch (pure function, no DB/LLM) ----


@pytest.mark.parametrize(
    "message, expected_tool",
    [
        ("Can I pay off my loan early with an extra 500 RON?", "early_repayment"),
        ("What rates and documents do you need for a mortgage?", "loan_products"),
        ("Do I have any pending loan applications?", "loan_applications"),
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


# ---- Romanian support: live-found via the assistant UI — "Vreau o rambursare
# anticipata de 500 RON la creditul meu" fell through every English-only
# keyword straight to the credit_score default, so the reply mixed a graceful
# LLM explanation with an unrelated raw credit-score summary dump instead of
# routing to early_repayment. ----


@pytest.mark.parametrize(
    "message, expected_tool",
    [
        ("Vreau o rambursare anticipata de 500 RON la creditul meu", "early_repayment"),
        ("Ce dobanda are un credit ipotecar?", "loan_products"),
        ("Am vreo cerere de credit in asteptare?", "loan_applications"),
        ("Care e rata mea lunara?", "monthly_payment"),
        ("Cat mai am de platit din credit?", "remaining_principal"),
        ("Arata-mi toate creditele mele", "loan_details"),
        ("Care e scorul meu de credit?", "credit_score"),
    ],
)
def test_select_tool_matches_expected_keyword_in_romanian(message, expected_tool):
    assert agent._select_tool(message) == expected_tool


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


def test_get_loan_products_uses_app_product_disclosures(db_session, seeded_user):
    result = tools.get_loan_products(ToolContext(user_id=seeded_user.id, db=db_session))
    names = {product.name for product in result}

    assert {"Personal loan", "Mortgage", "Auto loan", "Student loan", "Home improvement loan", "Debt consolidation loan"}.issubset(names)
    mortgage = next(product for product in result if product.product_type == LoanProductType.MORTGAGE)
    assert mortgage.representative_apr == Decimal("6.80")
    assert mortgage.collateral_required is True
    assert "Property documents" in mortgage.required_documents


def test_get_loan_applications_reuses_credit_service(db_session, seeded_user):
    service = CreditService(db_session)
    application = service.create_application(
        seeded_user.id,
        CreditApplicationCreate(
            type="PERSONAL_LOAN",
            loan_product_type=LoanProductType.MORTGAGE,
            requested_amount=Decimal("45000"),
            currency="RON",
            requested_term_months=120,
        ),
    )

    result = tools.get_loan_applications(ToolContext(user_id=seeded_user.id, db=db_session))

    assert len(result) == 1
    assert result[0].id == application.id
    assert result[0].loan_product_type == LoanProductType.MORTGAGE


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


def test_simulate_early_repayment_uses_exact_credit_service_contract(db_session, seeded_user, seeded_loan):
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)
    result = tools.simulate_early_repayment(ctx, Decimal("500"))
    expected = CreditService(db_session).simulate_early_repayment(seeded_user.id, seeded_loan.id, Decimal("500"))

    assert result is not None
    assert result == expected
    assert result.original_outstanding_principal == seeded_loan.outstanding_principal
    assert result.new_outstanding_principal == seeded_loan.outstanding_principal - Decimal("500")
    assert result.applied_extra_payment_amount == Decimal("500.00")
    assert result.term_months_reduced > 0
    assert result.total_interest_saved > 0


def test_simulate_early_repayment_caps_payment_at_outstanding_principal(db_session, seeded_user, seeded_loan):
    ctx = ToolContext(user_id=seeded_user.id, db=db_session)
    huge_payment = seeded_loan.outstanding_principal + Decimal("1000")

    result = tools.simulate_early_repayment(ctx, huge_payment)

    assert result is not None
    assert result.applied_extra_payment_amount == seeded_loan.outstanding_principal
    assert result.new_outstanding_principal == Decimal("0.00")
    assert result.revised_term_months == 0


# ---- agent.py: mocked at the tool-call/LLM boundary, never a live Azure call ----


def test_handle_combines_llm_explanation_with_exact_deterministic_figures(db_session, seeded_user, seeded_loan, monkeypatch):
    monkeypatch.setattr(agent, "_explain", lambda message, data_summary, history=None: "Mocked explanation.")

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
    monkeypatch.setattr(agent, "_explain", lambda message, data_summary, history=None: "Mocked explanation.")

    reply = agent.handle("can I pay off my loan early with an extra 500 RON?", seeded_user.id, db_session)

    assert reply.startswith("Mocked explanation.\n\n")
    assert "Interest saved" in reply
    assert "500" in reply


def test_handle_propagates_azure_not_configured_from_explain(db_session, seeded_user, seeded_loan, monkeypatch):
    def _raise_not_configured(message, data_summary, history=None):
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    monkeypatch.setattr(agent, "_explain", _raise_not_configured)

    with pytest.raises(AzureFoundryNotConfiguredError):
        agent.handle("what's my credit score?", seeded_user.id, db_session)


# ---- internal scoring leak fix: the raw reason_data (income_factor,
# debt_burden_penalty, etc.) must never reach the user or the LLM prompt in
# a reconstructible form — only a small set of fixed, qualitative phrases,
# computed deterministically in Python (never by the model).


def test_credit_score_directions_never_contain_internal_factor_names_or_digits():
    reason_data = {
        "base_score": 600,
        "income_factor": 240,
        "wallet_balance_factor": 0,
        "absolute_debt_penalty": 0,
        "debt_burden_penalty": 0,
        "existing_debt_penalty": 0,
    }
    directions = agent._credit_score_directions(reason_data)
    text = " ".join(directions)

    for key in reason_data:
        assert key not in text
    assert not any(char.isdigit() for char in text)


def test_credit_score_summary_never_contains_raw_reason_data_keys(db_session, seeded_user):
    summary = agent._credit_score(ToolContext(user_id=seeded_user.id, db=db_session))

    for key in ("income_factor", "wallet_balance_factor", "absolute_debt_penalty", "debt_burden_penalty", "existing_debt_penalty"):
        assert key not in summary


def test_system_prompt_forbids_reconstructing_internal_scoring_logic():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "never reveal, reconstruct, or paraphrase" in lowered
    assert "factor names, point values, weightings, or thresholds" in lowered


def test_append_summary_skips_the_append_when_the_llm_already_quoted_it_verbatim():
    summary = "Credit score: 664 (FAIR), calculated 2026-08-28.\nGeneral directions: income is contributing positively."
    explanation = f"Your score is in the FAIR category.\n\n---\n\n{summary}"

    assert agent._append_summary(explanation, summary) == explanation


def test_append_summary_appends_once_when_the_llm_did_not_quote_it():
    summary = "Credit score: 664 (FAIR), calculated 2026-08-28.\nGeneral directions: income is contributing positively."
    explanation = "Your score is in the FAIR category."

    assert agent._append_summary(explanation, summary) == f"{explanation}\n\n{summary}"


def test_system_prompt_includes_qualitative_credit_knowledge_verbatim():
    assert agent._CREDIT_KNOWLEDGE in agent._SYSTEM_PROMPT
    assert not any(char.isdigit() for char in agent._CREDIT_KNOWLEDGE)
