"""Typed tools for the Credit Agent (dev4-context.md §8 contract).

Every tool below only calls CreditService (credit/service.py, Dev 3's
module) and returns its result unmodified or a thin derived view — never
touches the DB/SQLAlchemy directly, never recalculates score/interest/
amortization math itself:

    Agent -> Tool -> Backend Service -> Database

calculate_monthly_payment() and get_remaining_principal() both read from
the same CreditService.list_loans() call: the service has no separate
"monthly payment" vs "remaining principal" method — both are just fields
on the same Loan record. Kept as two tools to match the §8 contract's
naming, not because the service distinguishes them.

simulate_early_repayment() is a best-effort approximation — see its own
docstring and ai/credit/README.md for exactly what's missing for an exact
version.
"""
import re
from decimal import Decimal, InvalidOperation

from app.ai.credit.schemas import EarlyRepaymentSimulation
from app.ai.observability import log_tool_call
from app.ai.tools.base import ToolContext
from app.core.exceptions import ValidationError
from app.credit.models import LoanInstallmentStatus, LoanStatus
from app.credit.schemas import CreditScorePublic, LoanCalculatorRequest, LoanPublic
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
def calculate_monthly_payment(ctx: ToolContext) -> list[LoanPublic]:
    """The user's current fixed monthly payment per active loan — already
    computed and stored at loan creation (Loan.monthly_payment), not
    recalculated here."""
    return [loan for loan in get_loan_details(ctx) if loan.status == LoanStatus.ACTIVE]


@log_tool_call
def get_remaining_principal(ctx: ToolContext) -> list[LoanPublic]:
    """Loan.outstanding_principal per active loan — maintained by
    CreditService as payments are made, not recalculated here."""
    return [loan for loan in get_loan_details(ctx) if loan.status == LoanStatus.ACTIVE]


def extract_amount(message: str) -> Decimal | None:
    """Simple heuristic for simulate_early_repayment()'s one required input:
    the largest number found in the message (e.g. "pay an extra 500 RON"
    -> 500). No real slot-filling/NLU, and no financial logic — this only
    decides which number in the text is "the amount", never computes with
    it. Can misfire on messages with multiple large numbers; a real parser
    is future work, not attempted here."""
    candidates: list[Decimal] = []
    for match in _NUMBER_RE.findall(message):
        try:
            candidates.append(Decimal(match.replace(",", "")))
        except InvalidOperation:
            continue
    return max(candidates) if candidates else None


@log_tool_call
def simulate_early_repayment(ctx: ToolContext, extra_payment_amount: Decimal) -> EarlyRepaymentSimulation | None:
    """Best-effort approximation — credit/service.py has no
    simulate_early_repayment() yet. Builds the closest sound estimate from
    what it does have, rather than inventing new financial logic:

    - Loan.outstanding_principal (exact: current balance)
    - LoanInstallment rows (exact: which installments remain unpaid, and
      their pre-computed interest_amount — summed for an exact "interest
      remaining under the current plan" baseline)
    - CreditService.calculate_loan(), the existing generic amortizer,
      re-run over (outstanding_principal - extra_payment_amount) for the
      SAME remaining term, to project a new monthly payment/total interest

    This models "keep the same remaining term, pay less per month" — not
    "keep the same payment, finish sooner" — because calculate_loan() has
    no inverse-term-solving mode; that's the main gap for an exact
    implementation (see ai/credit/README.md). It also assumes the extra
    payment lands exactly on an installment boundary, ignoring day-count
    interest accrual between payments. Returns None if the user has no
    active loan. Raises ValidationError for a non-positive amount.
    """
    if extra_payment_amount <= 0:
        raise ValidationError("extra_payment_amount must be positive")

    service = CreditService(ctx.db)
    loans = service.list_loans(ctx.user_id)
    loan = next((loan for loan in loans if loan.status == LoanStatus.ACTIVE), None)
    if loan is None:
        return None

    installments = service.list_installments_for_loan(ctx.user_id, loan.id)
    unpaid = [i for i in installments if i.status != LoanInstallmentStatus.PAID]
    remaining_term_months = len(unpaid)
    current_remaining_interest = sum((i.interest_amount for i in unpaid), Decimal("0"))

    outstanding_before = loan.outstanding_principal
    new_principal = outstanding_before - extra_payment_amount

    if new_principal <= 0:
        return EarlyRepaymentSimulation(
            loan_id=loan.id,
            currency=loan.currency,
            extra_payment_amount=extra_payment_amount,
            remaining_term_months=remaining_term_months,
            outstanding_principal_before=outstanding_before,
            principal_after_extra_payment=Decimal("0"),
            current_monthly_payment=loan.monthly_payment,
            current_remaining_interest=current_remaining_interest,
            new_monthly_payment=None,
            new_total_interest=Decimal("0"),
            interest_saved=current_remaining_interest,
            is_approximate=False,
            note="This extra payment fully repays the loan — no further interest accrues.",
        )

    projection = service.calculate_loan(
        LoanCalculatorRequest(
            principal_amount=new_principal,
            currency=loan.currency,
            annual_interest_rate=loan.interest_rate,
            term_months=remaining_term_months,
        )
    )

    return EarlyRepaymentSimulation(
        loan_id=loan.id,
        currency=loan.currency,
        extra_payment_amount=extra_payment_amount,
        remaining_term_months=remaining_term_months,
        outstanding_principal_before=outstanding_before,
        principal_after_extra_payment=new_principal,
        current_monthly_payment=loan.monthly_payment,
        current_remaining_interest=current_remaining_interest,
        new_monthly_payment=projection.monthly_payment,
        new_total_interest=projection.total_interest,
        interest_saved=current_remaining_interest - projection.total_interest,
        is_approximate=True,
        note=(
            "Approximate: re-amortizes the reduced principal over the same "
            "remaining term (lower payment, not a shorter term), and assumes "
            "the extra payment lands exactly on an installment boundary. "
            "credit/service.py has no simulate_early_repayment() yet — see "
            "ai/credit/README.md."
        ),
    )
