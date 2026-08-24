"""Orchestrator business logic: classify intent, then either answer directly
(greeting / out_of_scope) or route to the matching specialized agent.

Logs one line per step of this flow (request_received, agent_dispatched,
final_response/request_failed) tagged with a per-request correlation_id —
see ai/observability.py and ai/README.md for the format and how to watch
it live.
"""
import time
import uuid

from sqlalchemy.orm import Session

from app.ai.observability import bind_correlation_id, get_correlation_id, log_event, new_correlation_id
from app.ai.orchestrator.intent import IntentCategory, classify_intent
from app.ai.orchestrator.registry import AGENT_REGISTRY
from app.ai.orchestrator.schemas import OrchestratorChatResponse

_GREETING_REPLY = "Hi! I'm your banking assistant — ask me about your spending, budgets, savings, or credit."
_OUT_OF_SCOPE_REPLY = (
    "I'm a banking assistant and can only help with your accounts, spending, budgets, "
    "savings, and credit — I can't help with that request."
)


class OrchestratorService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def chat(self, user_id: uuid.UUID, message: str) -> OrchestratorChatResponse:
        bind_correlation_id(new_correlation_id())
        start = time.perf_counter()
        log_event("request_received", user_id=_mask_user_id(user_id), message_length=len(message))

        try:
            intent = classify_intent(message)

            if intent == IntentCategory.GREETING:
                log_event("agent_dispatched", agent="none", intent=intent.value)
                reply = _GREETING_REPLY
            elif intent == IntentCategory.OUT_OF_SCOPE:
                log_event("agent_dispatched", agent="none", intent=intent.value)
                reply = _OUT_OF_SCOPE_REPLY
            else:
                log_event("agent_dispatched", agent=intent.value, intent=intent.value)
                reply = AGENT_REGISTRY[intent](message, user_id, self.db)
        except Exception as exc:
            log_event(
                "request_failed",
                duration_ms=_elapsed_ms(start),
                error_type=type(exc).__name__,
            )
            raise

        log_event("final_response", intent=intent.value, duration_ms=_elapsed_ms(start))
        return OrchestratorChatResponse(intent=intent, reply=reply, correlation_id=get_correlation_id())


def _mask_user_id(user_id: uuid.UUID) -> str:
    return f"{str(user_id)[:8]}…"


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
