"""Pydantic schemas owned by the Credit Agent — not part of credit/schemas.py
(Dev 3's module) since these don't correspond to a real backend concept,
only to what this agent's tools compute on top of it."""
import uuid
from decimal import Decimal

from pydantic import BaseModel


class EarlyRepaymentSimulation(BaseModel):
    """Result of tools.simulate_early_repayment() — see that function's
    docstring and ai/credit/README.md for what's approximate and why.
    `current_*` fields are exact (read straight from the Loan/LoanInstallment
    records); `new_*`/`interest_saved` are approximate unless
    `is_approximate` is False (the full-payoff case, where "zero future
    interest" is exact)."""

    loan_id: uuid.UUID
    currency: str
    extra_payment_amount: Decimal
    remaining_term_months: int
    outstanding_principal_before: Decimal
    principal_after_extra_payment: Decimal
    current_monthly_payment: Decimal
    current_remaining_interest: Decimal
    new_monthly_payment: Decimal | None
    new_total_interest: Decimal | None
    interest_saved: Decimal | None
    is_approximate: bool
    note: str
