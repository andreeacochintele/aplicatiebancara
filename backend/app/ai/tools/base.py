"""Shared contract every agent's typed tools follow.

A tool's only job is to call a backend SERVICE and return its result —
never touch the database/SQLAlchemy directly (architecture.md §28, §44):

    Agent -> Tool -> Backend Service -> Database

`ToolContext` bundles what every tool needs (the authenticated user and a
DB session) so agent code doesn't wire each tool's dependencies by hand.
`ToolDataUnavailableError` is what a tool raises when the backend service
layer has no way to answer yet — an honest "not available", never a
guessed or recalculated figure (CLAUDE.md §12: deterministic financial
logic stays in backend services, and Claude must not invent it in the AI
layer either).
"""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ToolContext:
    user_id: uuid.UUID
    db: Session


class ToolDataUnavailableError(Exception):
    """Raised by a tool when the service layer doesn't yet expose the data
    it needs to answer. Callers (agents) must surface this honestly to the
    user rather than substituting an invented number."""
