"""Deterministic loan calculator utilities."""
from decimal import Decimal, ROUND_HALF_UP

from app.core.exceptions import ValidationError
from app.credit.schemas import LoanCalculatorRequest, LoanCalculatorResult, LoanInstallmentPreview

MONEY = Decimal("0.01")


def calculate_loan_schedule(data: LoanCalculatorRequest) -> LoanCalculatorResult:
    if data.principal_amount <= 0:
        raise ValidationError("Principal amount must be positive")
    if data.annual_interest_rate < 0:
        raise ValidationError("Annual interest rate cannot be negative")
    if data.term_months <= 0:
        raise ValidationError("Term months must be positive")

    principal = _money(data.principal_amount)
    monthly_rate = data.annual_interest_rate / Decimal("100") / Decimal("12")
    monthly_payment = _monthly_payment(principal, monthly_rate, data.term_months)

    remaining = principal
    total_payment = Decimal("0.00")
    total_interest = Decimal("0.00")
    schedule: list[LoanInstallmentPreview] = []

    for installment_number in range(1, data.term_months + 1):
        interest_amount = _money(remaining * monthly_rate)
        if installment_number == data.term_months:
            principal_amount = remaining
            payment_amount = _money(principal_amount + interest_amount)
        else:
            payment_amount = monthly_payment
            principal_amount = _money(payment_amount - interest_amount)
            if principal_amount > remaining:
                principal_amount = remaining
                payment_amount = _money(principal_amount + interest_amount)

        remaining = _money(remaining - principal_amount)
        total_payment = _money(total_payment + payment_amount)
        total_interest = _money(total_interest + interest_amount)

        schedule.append(
            LoanInstallmentPreview(
                installment_number=installment_number,
                payment_amount=payment_amount,
                principal_amount=principal_amount,
                interest_amount=interest_amount,
                remaining_principal=remaining,
            )
        )

    return LoanCalculatorResult(
        principal_amount=principal,
        annual_interest_rate=data.annual_interest_rate,
        term_months=data.term_months,
        monthly_payment=monthly_payment,
        total_payment=total_payment,
        total_interest=total_interest,
        schedule=schedule,
    )


def _monthly_payment(principal: Decimal, monthly_rate: Decimal, term_months: int) -> Decimal:
    if monthly_rate == 0:
        return _money(principal / Decimal(term_months))

    compound = (Decimal("1") + monthly_rate) ** term_months
    payment = principal * monthly_rate * compound / (compound - Decimal("1"))
    return _money(payment)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)
