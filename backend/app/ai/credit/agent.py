"""Credit Agent — STUB (Phase 5 skeleton).

Real implementation lands separately: tools wrapping the credit backend
service (score explanation, eligibility, remaining principal, early
repayment simulation — see architecture.md §31). All math stays in
tools/services, never in the LLM. For now this returns a fixed mock reply
so the Orchestrator's routing can be exercised end-to-end before that logic
exists.
"""
import uuid

from sqlalchemy.orm import Session

_MOCK_REPLY = "The Credit Agent isn't implemented yet — this is a placeholder reply from the orchestrator skeleton."


def handle(message: str, user_id: uuid.UUID, db: Session) -> str:
    return _MOCK_REPLY
