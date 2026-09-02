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

Every `reply` — whichever of the three sources below produced it — passes
through ai/guardrails.py's ensure_plain_text() before being persisted or
returned: this is the one place all of them converge, so it's also the one
place a "never raw JSON" guarantee can be enforced in code rather than
trusted to each agent's own system prompt alone.
"""
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.actions.schemas import AgentResult
from app.ai.guardrails import ensure_plain_text
from app.ai.observability import (
    bind_conversation_id,
    bind_correlation_id,
    get_correlation_id,
    log_event,
    new_correlation_id,
)
from app.ai.orchestrator.followups import generate_followup_questions
from app.ai.orchestrator.intent import IntentCategory, classify_intent
from app.ai.orchestrator.models import Conversation, ConversationMessage
from app.ai.orchestrator.registry import AGENT_REGISTRY
from app.ai.orchestrator.repository import ConversationRepository
from app.ai.orchestrator.schemas import ConversationMessagePublic, ConversationSummary, OrchestratorChatResponse
from app.ai.orchestrator.title import generate_conversation_title
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

    def chat(
        self,
        user_id: uuid.UUID,
        message: str,
        conversation_id: uuid.UUID | None = None,
        locale: str = "ro",
    ) -> OrchestratorChatResponse:
        bind_correlation_id(new_correlation_id())
        start = time.perf_counter()
        log_event("request_received", user_id=_mask_user_id(user_id), message_length=len(message))

        conversation = self._resolve_conversation(user_id, conversation_id)
        bind_conversation_id(str(conversation.id))
        history = self._load_history(conversation.id)

        action_card = None
        download = None
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
                agent_output = AGENT_REGISTRY[intent](message, user_id, self.db, history, locale)
                if isinstance(agent_output, AgentResult):
                    reply, action_card, download = agent_output.reply, agent_output.action_card, agent_output.download
                else:
                    reply = agent_output

            # Deterministic backstop, applied to every path (fixed greeting/
            # out_of_scope strings included) so the guarantee holds even if
            # one of those two ever stops being a hardcoded string later —
            # see ai/guardrails.py's own docstring for why this can't just
            # live in each agent's system prompt instead.
            reply = ensure_plain_text(reply)
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
        action_id = action_card.action_id if action_card is not None else None
        self._persist_turn(conversation, message, reply, agent_used, action_id)
        self._maybe_generate_title(conversation, message, reply)
        # Only for a routed personal_finance / credit / support reply.
        # Skipped for greeting/out_of_scope (fixed strings, no LLM call of
        # their own) and for the whole ACTION intent: the generic follow-up
        # model doesn't know what the actions agent can actually do, so it
        # invents options (pay by IBAN, add a beneficiary from chat, cancel
        # a payment) the agent can't honour — worse than no chips. An action
        # reply's real next step is the card's Accept/Cancel or a plain
        # rephrase.
        suggested_followups = (
            self._generate_followups(message, reply)
            if agent_used is not None and intent != IntentCategory.ACTION
            else []
        )

        log_event("final_response", intent=intent.value, duration_ms=_elapsed_ms(start))
        return OrchestratorChatResponse(
            intent=intent,
            reply=reply,
            correlation_id=get_correlation_id(),
            conversation_id=conversation.id,
            suggested_followups=suggested_followups,
            action_card=action_card,
            download=download,
        )

    def create_conversation(self, user_id: uuid.UUID) -> Conversation:
        return self.conversations.create_conversation(Conversation(user_id=user_id))

    def delete_conversation(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        conversation = self._get_owned_conversation(user_id, conversation_id)
        self.conversations.delete_conversation(conversation)

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
    ) -> list[ConversationMessagePublic]:
        """One page of `conversation_id`'s messages, chronological (oldest
        first, ready to render) — the most recent page by default, or the
        page immediately before `before` for loading older messages. Any
        message that drafted an agent action carries that action's current
        state inline (`.action`) so the UI redraws its confirm card with no
        extra round-trip. Raises NotFoundError if the conversation doesn't
        exist or doesn't belong to `user_id`."""
        self._get_owned_conversation(user_id, conversation_id)
        page = list(reversed(self.conversations.list_messages_for_conversation(conversation_id, limit=limit, before=before)))
        actions_by_id = self._actions_for_page(page)
        result: list[ConversationMessagePublic] = []
        for message in page:
            dto = ConversationMessagePublic.model_validate(message)
            if message.action_id is not None:
                dto.action = actions_by_id.get(message.action_id)
            result.append(dto)
        return result

    def _actions_for_page(self, page: list[ConversationMessage]) -> dict:
        action_ids = list({m.action_id for m in page if m.action_id is not None})
        if not action_ids:
            return {}
        # Lazy import: keeps ai/actions/ off this module's import graph at
        # load time (it pulls in the transaction engine), same pattern the
        # rest of the codebase uses to avoid cycles.
        from app.ai.actions.repository import AgentActionRepository
        from app.ai.actions.service import ActionService

        service = ActionService(self.db)
        return {
            action.id: service.public_view(action)
            for action in AgentActionRepository(self.db).list_by_ids(action_ids)
        }

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

    def _persist_turn(
        self,
        conversation: Conversation,
        message: str,
        reply: str,
        agent_used: str | None,
        action_id: uuid.UUID | None = None,
    ) -> None:
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
                action_id=action_id,
            )
        )
        self.conversations.touch_conversation(conversation, datetime.now(timezone.utc))

    def _maybe_generate_title(self, conversation: Conversation, message: str, reply: str) -> None:
        """Best-effort: only runs while `conversation.title` is still None
        (so exactly once per conversation — every later turn skips this),
        and a failure here (Azure not configured, API error, ...) is
        swallowed rather than raised, since the chat reply above has
        already been computed and persisted — a missing title must never
        turn an otherwise-successful chat request into a failed one."""
        if conversation.title is not None:
            return
        try:
            title = generate_conversation_title(message, reply)
        except Exception as exc:
            log_event("conversation_title_failed", error_type=type(exc).__name__)
            return
        if title:
            self.conversations.set_title(conversation, title)

    def _generate_followups(self, message: str, reply: str) -> list[str]:
        """Best-effort, same failure philosophy as _maybe_generate_title:
        only called for a routed agent reply (see chat()), and a failure
        here (Azure not configured, API error, ...) is swallowed rather
        than raised — the chat reply above has already been computed and
        persisted, so a missing suggestion list must never turn an
        otherwise-successful chat request into a failed one."""
        try:
            return generate_followup_questions(message, reply)
        except Exception as exc:
            log_event("followup_questions_failed", error_type=type(exc).__name__)
            return []


def _mask_user_id(user_id: uuid.UUID) -> str:
    return f"{str(user_id)[:8]}…"


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
