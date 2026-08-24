"""Support Agent — STUB (Phase 5 skeleton).

Not part of the originally planned agent set (architecture.md §29-32) —
added as a 5th orchestrator intent category to hold general account/app
help that isn't personal_finance or credit. Returns a fixed mock reply so
the Orchestrator's routing can be exercised end-to-end before real logic
exists.
"""
import uuid

from sqlalchemy.orm import Session

_MOCK_REPLY = "The Support Agent isn't implemented yet — this is a placeholder reply from the orchestrator skeleton."


def handle(message: str, user_id: uuid.UUID, db: Session) -> str:
    return _MOCK_REPLY
