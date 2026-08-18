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
    income_factor = min(_as_int(income / Decimal("1000") * Decimal("5")), 120)
    wallet_factor = min(_as_int(wallet_balance / Decimal("1000") * Decimal("4")), 80)
    debt_penalty = min(_as_int(existing_debt / Decimal("1000") * Decimal("8")), 160)

    score = max(300, min(850, 600 + income_factor + wallet_factor - debt_penalty))
    return score, {
        "base_score": 600,
        "income_factor": income_factor,
        "wallet_balance_factor": wallet_factor,
        "existing_debt_penalty": debt_penalty,
    }
