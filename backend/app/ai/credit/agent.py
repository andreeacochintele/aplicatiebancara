"""Credit Agent.

Picks one tool from tools.py based on simple keyword matching on the
user's message, calls it, formats its result into an exact deterministic
summary (no LLM involved in producing the numbers), then asks the shared
Azure GPT-5-mini client for a short natural-language framing of that
summary only — same pattern as ai/personal_finance/agent.py. The figures
the user sees come verbatim from the formatted summary; the LLM never
recalculates or rounds them (CLAUDE.md §12, §14).

No `temperature=` kwarg anywhere below: this GPT-5-mini deployment is a
reasoning model that only accepts the default and 400s otherwise
(confirmed live during the orchestrator work — see
ai/client/azure_foundry_client.py's module docstring).

simulate_early_repayment is the one tool that needs an input beyond "the
current user" (an extra-payment amount), so it's dispatched separately
from the other four rather than through the uniform ctx-only _SUMMARIZERS
table.

`history` (from ai/orchestrator/service.py's short-term conversation
memory) is passed through to the LLM explanation call as prior context —
it never affects which tool gets picked; tool selection is keyword-only
on the current message, same as before history existed.
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
    "You are the Credit Agent of a banking assistant. You will be shown the "
    "user's real credit/loan data, already fetched from backend services and "
    "quoted to the user verbatim right after your reply — do not restate, "
    "recalculate, or invent any figure yourself. Write only a short (1-3 "
    "sentence), friendly answer to the user's message using that data as "
    "context. If a figure is marked approximate, say so plainly rather than "
    "presenting it as exact."
)

_NO_AMOUNT_REPLY = "How much extra would you like to pay toward your loan? Let me know an amount and I can simulate it."

# First keyword match wins; early_repayment is checked first since its
# phrasing ("pay off my loan early") would otherwise match loan_details.
_DISPATCH: list[tuple[str, tuple[str, ...]]] = [
    ("early_repayment", ("early repayment", "pay off", "payoff", "extra payment", "pay extra", "overpay")),
    ("monthly_payment", ("monthly payment", "installment", "how much do i pay", "payment amount")),
    ("remaining_principal", ("remaining principal", "how much do i owe", "outstanding", "left to pay")),
    ("loan_details", ("loan", "loans")),
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
        {"role": "user", "content": f"User asked: {message}\n\nData:\n{data_summary}"},
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
        return "Loans: none found."
    lines = [
        f"- {loan.status.value} loan: {loan.principal_amount} {loan.currency} principal at "
        f"{loan.interest_rate}% over {loan.term_months} months, {loan.monthly_payment} {loan.currency}/month, "
        f"{loan.outstanding_principal} {loan.currency} outstanding, started {loan.start_date}, "
        f"matures {loan.maturity_date}"
        for loan in loans
    ]
    return "Loans:\n" + "\n".join(lines)


def _monthly_payment(ctx: ToolContext) -> str:
    loans = tools.calculate_monthly_payment(ctx)
    if not loans:
        return "Monthly payment: no active loan found."
    lines = [f"- {loan.monthly_payment} {loan.currency}/month (loan started {loan.start_date})" for loan in loans]
    return "Current monthly payment(s):\n" + "\n".join(lines)


def _remaining_principal(ctx: ToolContext) -> str:
    loans = tools.get_remaining_principal(ctx)
    if not loans:
        return "Remaining principal: no active loan found."
    lines = [
        f"- {loan.outstanding_principal} {loan.currency} remaining (of {loan.principal_amount} {loan.currency} original)"
        for loan in loans
    ]
    return "Remaining principal:\n" + "\n".join(lines)


def _early_repayment(ctx: ToolContext, amount: Decimal) -> str:
    result = tools.simulate_early_repayment(ctx, amount)
    if result is None:
        return "Early repayment simulation: no active loan found to simulate against."

    if result.new_monthly_payment is None:
        return (
            f"Early repayment simulation (exact): paying an extra {result.extra_payment_amount} "
            f"{result.currency} fully repays the loan (outstanding was "
            f"{result.outstanding_principal_before} {result.currency}). {result.note}"
        )

    return (
        f"Early repayment simulation (approximate — {result.note}):\n"
        f"- Extra payment: {result.extra_payment_amount} {result.currency}\n"
        f"- Outstanding principal before: {result.outstanding_principal_before} {result.currency}\n"
        f"- Principal after extra payment: {result.principal_after_extra_payment} {result.currency}\n"
        f"- Remaining term: {result.remaining_term_months} months (unchanged)\n"
        f"- Current monthly payment: {result.current_monthly_payment} {result.currency}\n"
        f"- Projected new monthly payment: {result.new_monthly_payment} {result.currency}\n"
        f"- Interest remaining under current plan: {result.current_remaining_interest} {result.currency}\n"
        f"- Projected new total interest: {result.new_total_interest} {result.currency}\n"
        f"- Estimated interest saved: {result.interest_saved} {result.currency}"
    )


_SUMMARIZERS = {
    "credit_score": _credit_score,
    "loan_details": _loan_details,
    "monthly_payment": _monthly_payment,
    "remaining_principal": _remaining_principal,
}
