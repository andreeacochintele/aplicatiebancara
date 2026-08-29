"""Lightweight pre-execution fraud screen for agent-initiated transfers.

Deliberately NOT the full deterministic fraud engine (app/fraud/service.py).
That engine does now cover transfers — it scores them, holds the funds, opens
a FraudCase and lets an admin approve/reject (approve() credits the
destination too) — but it can only act once the transfer is actually being
executed. This screen runs one step earlier, when the agent proposes to act,
and blocks by parking the AgentAction in NEEDS_REVIEW so nothing executes at
all. The two are complementary: this one prevents an agent-initiated attempt,
the engine holds a transfer that does get attempted.

For v1 the meaningful controls are the hard limits (≤ 500 RON, recipient
must be an already-saved beneficiary, explicit human confirm). This screen
adds a soft check on top: an untrusted current device, or a burst of agent
transfers. A hit parks the AgentAction in NEEDS_REVIEW and executes
nothing — no funds move, no fraud case, no hold.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.observability import log_event
from app.fraud.service import FraudService

# A burst of this many agent transfers already executed inside the window
# (see repository.count_recent_executed) trips the screen.
RAPID_TRANSFER_LIMIT = 3


@dataclass
class ScreenResult:
    blocked: bool
    reasons: list[str] = field(default_factory=list)


def screen_transfer(db: Session, user_id, recent_executed_count: int) -> ScreenResult:
    reasons: list[str] = []

    devices = FraudService(db).get_known_devices(user_id)
    latest = devices[0] if devices else None
    if latest is not None and not latest.trusted:
        reasons.append("UNTRUSTED_DEVICE")

    if recent_executed_count >= RAPID_TRANSFER_LIMIT:
        reasons.append("RAPID_TRANSFERS")

    result = ScreenResult(blocked=bool(reasons), reasons=reasons)
    if result.blocked:
        log_event("agent_action_fraud_screen", status="blocked", reasons=",".join(reasons))
    return result
