"""Typed tools for the Credit Agent.

Every tool below follows the app rule:

    AI Agent -> Tool -> Backend Service -> Database

The agent can read and simulate credit data, but it does not execute
payments or approve loans. Deterministic credit math stays in CreditService.
"""
import re
from decimal import Decimal, InvalidOperation

from app.ai.observability import log_tool_call
from app.ai.tools.base import ToolContext
from app.core.exceptions import ValidationError
from app.credit.models import LoanStatus
from app.credit.schemas import CreditApplicationPublic, CreditScorePublic, EarlyRepaymentResult, LoanProductPublic, LoanPublic
from app.credit.service import CreditService

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


@log_tool_call
def get_credit_score(ctx: ToolContext) -> CreditScorePublic:
    return CreditService(ctx.db).get_score(ctx.user_id)


@log_tool_call
def get_loan_details(ctx: ToolContext) -> list[LoanPublic]:
    loans = CreditService(ctx.db).list_loans(ctx.user_id)
    return [LoanPublic.model_validate(loan) for loan in loans]


@log_tool_call
def get_loan_products(ctx: ToolContext) -> list[LoanProductPublic]:
    return CreditService(ctx.db).list_loan_products()


@log_tool_call
def get_loan_applications(ctx: ToolContext) -> list[CreditApplicationPublic]:
    applications = CreditService(ctx.db).list_applications(ctx.user_id)
    return [CreditApplicationPublic.model_validate(application) for application in applications]


@log_tool_call
def calculate_monthly_payment(ctx: ToolContext) -> list[LoanPublic]:
    return [loan for loan in get_loan_details(ctx) if loan.status == LoanStatus.ACTIVE]


@log_tool_call
def get_remaining_principal(ctx: ToolContext) -> list[LoanPublic]:
    return [loan for loan in get_loan_details(ctx) if loan.status == LoanStatus.ACTIVE]


def extract_amount(message: str) -> Decimal | None:
    candidates: list[Decimal] = []
    for match in _NUMBER_RE.findall(message):
        try:
            candidates.append(Decimal(match.replace(",", "")))
        except InvalidOperation:
            continue
    return max(candidates) if candidates else None


@log_tool_call
def simulate_early_repayment(ctx: ToolContext, extra_payment_amount: Decimal) -> EarlyRepaymentResult | None:
    """Simulate an extra principal payment using the real credit service.

    CreditService keeps the current monthly payment and calculates the shorter
    payoff term, interest saved, and new outstanding balance.
    """
    if extra_payment_amount <= 0:
        raise ValidationError("extra_payment_amount must be positive")

    service = CreditService(ctx.db)
    loan = next((candidate for candidate in service.list_loans(ctx.user_id) if candidate.status == LoanStatus.ACTIVE), None)
    if loan is None:
        return None
    return service.simulate_early_repayment(ctx.user_id, loan.id, extra_payment_amount)
