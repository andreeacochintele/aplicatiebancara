"""Orchestrator business logic: classify intent, then either answer directly
(greeting / out_of_scope) or route to the matching specialized agent.

Short-term conversation memory: the last HISTORY_LIMIT messages for this
user (chronological) are loaded before dispatch and passed as context to
BOTH the intent classifier and whichever agent is dispatched — see
intent.py and each agent's own docstring for how they use it.
Intent classification is re-run fresh on every message; history is
disambiguation context, never a reason to stick with the previous turn's
agent (see intent.py's system prompt, and
test_ai_conversation_history.py's topic-switch test).

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
from app.ai.orchestrator.models import ConversationMessage
from app.ai.orchestrator.registry import AGENT_REGISTRY
from app.ai.orchestrator.repository import ConversationRepository
from app.ai.orchestrator.schemas import OrchestratorChatResponse

HISTORY_LIMIT = 8

_GREETING_REPLY = "Hi! I'm your banking assistant — ask me about your spending, budgets, savings, or credit."
_OUT_OF_SCOPE_REPLY = (
    "I'm a banking assistant and can only help with your accounts, spending, budgets, "
    "savings, and credit — I can't help with that request."
)


class OrchestratorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.conversations = ConversationRepository(db)

    def chat(self, user_id: uuid.UUID, message: str) -> OrchestratorChatResponse:
        bind_correlation_id(new_correlation_id())
        start = time.perf_counter()
        log_event("request_received", user_id=_mask_user_id(user_id), message_length=len(message))

        history = self._load_history(user_id)

        try:
            intent = classify_intent(message, history)

            if intent == IntentCategory.GREETING:
                log_event("agent_dispatched", agent="none", intent=intent.value)
                reply = _GREETING_REPLY
            elif intent == IntentCategory.OUT_OF_SCOPE:
                log_event("agent_dispatched", agent="none", intent=intent.value)
                reply = _OUT_OF_SCOPE_REPLY
            else:
                log_event("agent_dispatched", agent=intent.value, intent=intent.value)
                reply = AGENT_REGISTRY[intent](message, user_id, self.db, history)
        except Exception as exc:
            log_event(
                "request_failed",
                duration_ms=_elapsed_ms(start),
                error_type=type(exc).__name__,
            )
            raise

        # Only persisted once we have a complete (question, answer) pair —
        # a request that raised above leaves nothing written, so history
        # never contains a dangling user message with no reply.
        agent_used = intent.value if intent in AGENT_REGISTRY else None
        self._persist_turn(user_id, message, reply, agent_used)

        log_event("final_response", intent=intent.value, duration_ms=_elapsed_ms(start))
        return OrchestratorChatResponse(intent=intent, reply=reply, correlation_id=get_correlation_id())

    def _load_history(self, user_id: uuid.UUID) -> list[dict[str, str]]:
        recent = self.conversations.list_recent_for_user(user_id, limit=HISTORY_LIMIT)
        chronological = reversed(recent)  # repository returns newest-first
        return [{"role": row.role, "content": row.content} for row in chronological]

    def _persist_turn(self, user_id: uuid.UUID, message: str, reply: str, agent_used: str | None) -> None:
        self.conversations.add(ConversationMessage(user_id=user_id, role="user", content=message, agent_used=None))
        self.conversations.add(
            ConversationMessage(user_id=user_id, role="assistant", content=reply, agent_used=agent_used)
        )


def _mask_user_id(user_id: uuid.UUID) -> str:
    return f"{str(user_id)[:8]}…"


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
