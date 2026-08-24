"""Personal Finance Agent — STUB (Phase 5 skeleton).

Real implementation lands separately: tools wrapping analytics/budgets/
savings services (spending analysis, budgets, savings goals, cash-flow
forecasting, cashback — see architecture.md §30). For now this returns a
fixed mock reply so the Orchestrator's routing can be exercised end-to-end
before that logic exists.
"""
import uuid

from sqlalchemy.orm import Session

_MOCK_REPLY = "The Personal Finance Agent isn't implemented yet — this is a placeholder reply from the orchestrator skeleton."


def handle(message: str, user_id: uuid.UUID, db: Session) -> str:
    return _MOCK_REPLY
