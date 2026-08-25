"""Deterministic mock credit scoring rules."""
from decimal import Decimal, ROUND_HALF_UP


def _as_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def credit_band(score: int) -> str:
    if score >= 800:
        return "EXCELLENT"
    if score >= 740:
        return "VERY_GOOD"
    if score >= 670:
        return "GOOD"
    if score >= 580:
        return "FAIR"
    return "POOR"


def calculate_credit_score(income: Decimal, existing_debt: Decimal, wallet_balance: Decimal) -> tuple[int, dict[str, int]]:
    income_factor = min(_as_int(income / Decimal("1000") * Decimal("8")), 240)
    net_wallet_balance = max(wallet_balance - existing_debt, Decimal("0"))
    wallet_factor = min(_as_int(net_wallet_balance / Decimal("1000") * Decimal("2.5")), 90)
    absolute_debt_penalty = 0
    if existing_debt <= 0:
        debt_burden_penalty = 0
    elif income <= 0:
        debt_burden_penalty = 180
    else:
        annual_income_capacity = income * Decimal("12")
        debt_burden_penalty = min(_as_int(existing_debt / annual_income_capacity * Decimal("180")), 180)
    debt_penalty = absolute_debt_penalty + debt_burden_penalty

    score = max(300, min(850, 600 + income_factor + wallet_factor - debt_penalty))
    return score, {
        "base_score": 600,
        "income_factor": income_factor,
        "wallet_balance_factor": wallet_factor,
        "absolute_debt_penalty": absolute_debt_penalty,
        "debt_burden_penalty": debt_burden_penalty,
        "existing_debt_penalty": debt_penalty,
    }
