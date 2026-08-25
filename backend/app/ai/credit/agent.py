"""Credit Agent.

Routes credit questions to deterministic tools, formats the exact tool output,
then lets the shared Azure GPT-5-mini client provide a short conversational
framing. The LLM never calculates credit figures or makes approval decisions.
"""
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.credit import tools
from app.ai.observability import log_debug, timed_event
from app.ai.tools.base import ToolContext
from app.core.exceptions import ValidationError

_SYSTEM_PROMPT = (
    "You are the Credit Agent inside this banking app. You can explain only the "
    "credit features the app actually offers: credit score, loan products, loan "
    "applications, active loan balances, monthly payments, repayment schedules, "
    "and early repayment simulations. Use the deterministic backend summary as "
    "the source of truth. Do not invent rates, eligibility, legal consequences, "
    "documents, balances, approvals, or payment outcomes. Do not say you can "
    "approve loans or execute payments. Keep the answer short, clear, and "
    "product-specific."
)

_NO_AMOUNT_REPLY = "How much extra would you like to simulate toward your active loan?"

_DISPATCH: list[tuple[str, tuple[str, ...]]] = [
    ("early_repayment", ("early repayment", "pay off", "payoff", "extra payment", "pay extra", "overpay")),
    ("loan_products", ("loan type", "loan product", "rates", "rate", "apr", "documents", "obligations", "liabilities", "legal")),
    ("loan_applications", ("application", "approved", "pending", "offer")),
    ("monthly_payment", ("monthly payment", "installment", "instalment", "how much do i pay", "payment amount")),
    ("remaining_principal", ("remaining principal", "how much do i owe", "outstanding", "left to pay", "balance remaining")),
    ("loan_details", ("loan", "loans", "repayment schedule", "schedule")),
    ("credit_score", ("credit score", "score", "credit rating", "eligib")),
]
_DEFAULT_TOOL = "credit_score"


def handle(message: str, user_id: uuid.UUID, db: Session, history: list[dict[str, str]] | None = None) -> str:
    ctx = ToolContext(user_id=user_id, db=db)
    tool_name = _select_tool(message)

    if tool_name == "early_repayment":
        amount = tools.extract_amount(message)
        if amount is None:
            return _NO_AMOUNT_REPLY
        try:
            summary = _early_repayment(ctx, amount)
        except ValidationError as exc:
            return str(exc)
    else:
        summary = _SUMMARIZERS[tool_name](ctx)

    explanation = _explain(message, summary, history)
    return f"{explanation}\n\n{summary}"


def _select_tool(message: str) -> str:
    lowered = message.lower()
    for tool_name, keywords in _DISPATCH:
        if any(keyword in lowered for keyword in keywords):
            return tool_name
    return _DEFAULT_TOOL


def _explain(message: str, data_summary: str, history: list[dict[str, str]] | None = None) -> str:
    client = get_azure_foundry_client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *(history or []),
        {"role": "user", "content": f"User asked: {message}\n\nBackend summary:\n{data_summary}"},
    ]
    log_debug("llm_call.request", agent="credit", messages=messages)
    with timed_event("llm_call", agent="credit"):
        response = client.chat_completion(messages=messages)
    content = response.choices[0].message.content.strip()
    log_debug("llm_call.response", agent="credit", content=content)
    return content


def _credit_score(ctx: ToolContext) -> str:
    score = tools.get_credit_score(ctx)
    factors = ", ".join(f"{key}: {value}" for key, value in score.reason_data.items())
    return f"Credit score: {score.score} ({score.band}), calculated {score.calculated_at.date()}.\nFactors: {factors}"


def _loan_details(ctx: ToolContext) -> str:
    loans = tools.get_loan_details(ctx)
    if not loans:
        return "Loans: no active or historical loans found."
    lines = [
        f"- {loan.status.value}: {loan.principal_amount} {loan.currency} principal, "
        f"{loan.interest_rate}% APR, {loan.term_months} months, "
        f"{loan.monthly_payment} {loan.currency}/month, "
        f"{loan.outstanding_principal} {loan.currency} outstanding, "
        f"next payment {loan.next_payment_date}, matures {loan.maturity_date}"
        for loan in loans
    ]
    return "Loans:\n" + "\n".join(lines)


def _loan_products(ctx: ToolContext) -> str:
    products = tools.get_loan_products(ctx)
    lines = []
    for product in products:
        lines.append(
            f"- {product.name}: representative APR {product.representative_apr}%, typical term "
            f"{product.typical_term_months}. Documents: {', '.join(product.required_documents)}. "
            f"Obligations: {'; '.join(product.obligations)} Liabilities: {'; '.join(product.liabilities)}"
        )
    return "Loan products currently offered by the app:\n" + "\n".join(lines)


def _loan_applications(ctx: ToolContext) -> str:
    applications = tools.get_loan_applications(ctx)
    if not applications:
        return "Loan applications: none found."
    lines = [
        f"- {application.status.value}: {application.loan_product_type.value if application.loan_product_type else 'loan'} "
        f"for {application.requested_amount} {application.currency}, "
        f"term {application.requested_term_months or 'N/A'} months, "
        f"score at application {application.credit_score_at_application}, "
        f"offered amount {application.offered_amount or 'N/A'}, offered APR {application.offered_interest_rate or 'N/A'}"
        for application in applications
    ]
    return "Loan applications:\n" + "\n".join(lines)


def _monthly_payment(ctx: ToolContext) -> str:
    loans = tools.calculate_monthly_payment(ctx)
    if not loans:
        return "Monthly payment: no active loan found."
    lines = [f"- {loan.monthly_payment} {loan.currency}/month for {loan.outstanding_principal} {loan.currency} outstanding" for loan in loans]
    return "Current monthly payment(s):\n" + "\n".join(lines)


def _remaining_principal(ctx: ToolContext) -> str:
    loans = tools.get_remaining_principal(ctx)
    if not loans:
        return "Remaining principal: no active loan found."
    lines = [
        f"- {loan.outstanding_principal} {loan.currency} remaining from {loan.principal_amount} {loan.currency} original principal"
        for loan in loans
    ]
    return "Remaining principal:\n" + "\n".join(lines)


def _early_repayment(ctx: ToolContext, amount: Decimal) -> str:
    result = tools.simulate_early_repayment(ctx, amount)
    if result is None:
        return "Early repayment simulation: no active loan found to simulate against."

    return (
        "Early repayment simulation:\n"
        f"- Extra payment requested: {result.extra_payment_amount} {result.currency}\n"
        f"- Extra payment applied: {result.applied_extra_payment_amount} {result.currency}\n"
        f"- Outstanding before: {result.original_outstanding_principal} {result.currency}\n"
        f"- Outstanding after: {result.new_outstanding_principal} {result.currency}\n"
        f"- Remaining term now: {result.remaining_term_months} months\n"
        f"- Revised term after extra payment: {result.revised_term_months} months\n"
        f"- Months reduced: {result.term_months_reduced}\n"
        f"- Interest before: {result.total_interest_before} {result.currency}\n"
        f"- Interest after: {result.total_interest_after} {result.currency}\n"
        f"- Interest saved: {result.total_interest_saved} {result.currency}\n"
        "This is a simulation only; making the actual payment is handled by the Credit page payment flow."
    )


_SUMMARIZERS = {
    "credit_score": _credit_score,
    "loan_details": _loan_details,
    "loan_products": _loan_products,
    "loan_applications": _loan_applications,
    "monthly_payment": _monthly_payment,
    "remaining_principal": _remaining_principal,
}
