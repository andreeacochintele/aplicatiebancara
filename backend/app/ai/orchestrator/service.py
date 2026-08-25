"""Orchestrator business logic: classify intent, then either answer directly
(greeting / out_of_scope) or route to the matching specialized agent.

Conversation threading (migration 0031): every chat turn belongs to a
Conversation, and short-term LLM context (HISTORY_LIMIT messages) is always
scoped to that ONE conversation — never bled across a user's other
conversations. If a chat request doesn't name a conversation_id, a new
conversation is created automatically (naive/first-message clients still
work with no extra round-trip).

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
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.observability import bind_correlation_id, get_correlation_id, log_event, new_correlation_id
from app.ai.orchestrator.intent import IntentCategory, classify_intent
from app.ai.orchestrator.models import Conversation, ConversationMessage
from app.ai.orchestrator.registry import AGENT_REGISTRY
from app.ai.orchestrator.repository import ConversationRepository
from app.ai.orchestrator.schemas import ConversationSummary, OrchestratorChatResponse
from app.core.exceptions import NotFoundError

HISTORY_LIMIT = 8  # messages fed to the LLM as context — see _load_history()

# Default page size for the paginated messages-by-conversation endpoint.
MESSAGES_PAGE_LIMIT = 50

_GREETING_REPLY_EN = "Hi! I'm your banking assistant — ask me about your spending, budgets, savings, or credit."
_GREETING_REPLY_RO = "Salut! Sunt asistentul tău bancar — întreabă-mă despre cheltuieli, bugete, economii sau credit."
_OUT_OF_SCOPE_REPLY_EN = (
    "I'm a banking assistant and can only help with your accounts, spending, budgets, "
    "savings, and credit — I can't help with that request."
)
_OUT_OF_SCOPE_REPLY_RO = (
    "Sunt un asistent bancar și te pot ajuta doar cu contul tău, cheltuieli, bugete, "
    "economii și credit — nu te pot ajuta cu această cerere."
)

# GREETING/OUT_OF_SCOPE are the only two paths in the whole orchestrator with
# no LLM call at all (see chat() below) — deliberately cheap/deterministic.
# Matching reply language here the same way (a keyword/diacritic heuristic,
# not a model call) keeps that property instead of adding an LLM round-trip
# just to pick between two fixed strings.
_ROMANIAN_DIACRITICS = set("ăâîșşțţĂÂÎȘŞȚŢ")
_ROMANIAN_WORDS = (
    "salut", "salutare", "buna", "bună", "servus", "neata", "ce faci", "ce mai faci",
    "cum esti", "cum ești", "multumesc", "mulțumesc", "mersi", "va rog", "vă rog",
    "da", "nu", "unde", "cand", "când", "cum", "cat", "cât", "vreau", "poti", "poți",
    "ajutor", "buna ziua", "bună ziua", "sunt",
)
_ENGLISH_WORDS = (
    "hi", "hello", "hey", "thanks", "thank you", "please", "yes", "no", "what",
    "how", "when", "where", "help", "good morning", "good evening",
)

_PREVIEW_LENGTH = 140


def _reply_in_romanian(message: str) -> bool:
    """Cheap RO/EN detection for the two static replies above. Explicit
    Romanian signal (diacritics or a common word) wins; explicit English
    signal wins if no Romanian signal is present; a genuinely ambiguous or
    too-short message (neither list matches — e.g. a bare emoji or "ok")
    defaults to Romanian, matching the app's primary market (RON, Romanian
    seed data) — same default the two LLM-backed agents are instructed to
    use for the same situation."""
    lowered = message.lower()
    if any(ch in _ROMANIAN_DIACRITICS for ch in message):
        return True
    if any(word in lowered for word in _ROMANIAN_WORDS):
        return True
    if any(word in lowered for word in _ENGLISH_WORDS):
        return False
    return True


class OrchestratorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.conversations = ConversationRepository(db)

    def chat(self, user_id: uuid.UUID, message: str, conversation_id: uuid.UUID | None = None) -> OrchestratorChatResponse:
        bind_correlation_id(new_correlation_id())
        start = time.perf_counter()
        log_event("request_received", user_id=_mask_user_id(user_id), message_length=len(message))

        conversation = self._resolve_conversation(user_id, conversation_id)
        history = self._load_history(conversation.id)

        try:
            intent = classify_intent(message, history)

            if intent == IntentCategory.GREETING:
                log_event("agent_dispatched", agent="none", intent=intent.value)
                reply = _GREETING_REPLY_RO if _reply_in_romanian(message) else _GREETING_REPLY_EN
            elif intent == IntentCategory.OUT_OF_SCOPE:
                log_event("agent_dispatched", agent="none", intent=intent.value)
                reply = _OUT_OF_SCOPE_REPLY_RO if _reply_in_romanian(message) else _OUT_OF_SCOPE_REPLY_EN
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
        self._persist_turn(conversation, message, reply, agent_used)

        log_event("final_response", intent=intent.value, duration_ms=_elapsed_ms(start))
        return OrchestratorChatResponse(
            intent=intent, reply=reply, correlation_id=get_correlation_id(), conversation_id=conversation.id
        )

    def create_conversation(self, user_id: uuid.UUID) -> Conversation:
        return self.conversations.create_conversation(Conversation(user_id=user_id))

    def list_conversations(self, user_id: uuid.UUID, limit: int = 50) -> list[ConversationSummary]:
        conversations = self.conversations.list_conversations_for_user(user_id, limit=limit)
        summaries = []
        for conversation in conversations:
            last_message = self.conversations.get_last_message_for_conversation(conversation.id)
            preview = last_message.content[:_PREVIEW_LENGTH] if last_message is not None else None
            summaries.append(
                ConversationSummary(
                    id=conversation.id,
                    title=conversation.title,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                    last_message_preview=preview,
                )
            )
        return summaries

    def get_conversation_messages(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        limit: int = MESSAGES_PAGE_LIMIT,
        before: datetime | None = None,
    ) -> list[ConversationMessage]:
        """One page of `conversation_id`'s messages, chronological (oldest
        first, ready to render) — the most recent page by default, or the
        page immediately before `before` for loading older messages.
        Raises NotFoundError if the conversation doesn't exist or doesn't
        belong to `user_id` (never leaks another user's conversation)."""
        self._get_owned_conversation(user_id, conversation_id)
        page = self.conversations.list_messages_for_conversation(conversation_id, limit=limit, before=before)
        return list(reversed(page))

    def _resolve_conversation(self, user_id: uuid.UUID, conversation_id: uuid.UUID | None) -> Conversation:
        if conversation_id is None:
            return self.create_conversation(user_id)
        return self._get_owned_conversation(user_id, conversation_id)

    def _get_owned_conversation(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
        conversation = self.conversations.get_conversation(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise NotFoundError("Conversation not found")
        return conversation

    def _load_history(self, conversation_id: uuid.UUID) -> list[dict[str, str]]:
        recent = self.conversations.list_recent_for_conversation(conversation_id, limit=HISTORY_LIMIT)
        chronological = reversed(recent)  # repository returns newest-first
        return [{"role": row.role, "content": row.content} for row in chronological]

    def _persist_turn(self, conversation: Conversation, message: str, reply: str, agent_used: str | None) -> None:
        self.conversations.add(
            ConversationMessage(
                user_id=conversation.user_id, conversation_id=conversation.id, role="user", content=message, agent_used=None
            )
        )
        self.conversations.add(
            ConversationMessage(
                user_id=conversation.user_id,
                conversation_id=conversation.id,
                role="assistant",
                content=reply,
                agent_used=agent_used,
            )
        )
        self.conversations.touch_conversation(conversation, datetime.now(timezone.utc))


def _mask_user_id(user_id: uuid.UUID) -> str:
    return f"{str(user_id)[:8]}…"


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
