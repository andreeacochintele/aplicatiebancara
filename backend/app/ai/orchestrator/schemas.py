"""Pydantic schemas for the Orchestrator Agent's chat/conversation endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.ai.actions.schemas import ActionCard
from app.ai.orchestrator.intent import IntentCategory


class OrchestratorChatRequest(BaseModel):
    message: str
    # Omit to auto-create a new conversation (naive/first-message clients
    # still work) — see OrchestratorService.chat().
    conversation_id: uuid.UUID | None = None


class OrchestratorChatResponse(BaseModel):
    intent: IntentCategory
    reply: str
    correlation_id: str
    conversation_id: uuid.UUID
    # 2-3 clickable next-question suggestions — only populated for a routed
    # agent reply (personal_finance/credit/support), always empty for
    # greeting/out_of_scope and for an action-card reply.
    # See OrchestratorService._generate_followups().
    suggested_followups: list[str] = Field(default_factory=list)
    # Set only when the actions agent drafted something needing confirmation
    # (see ai/actions/). The frontend renders it as an interactive card; the
    # user's Accept hits POST /ai/actions/{id}/confirm. Not persisted in
    # conversation history (same as suggested_followups).
    action_card: ActionCard | None = None


class ConversationMessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    agent_used: str | None
    # Present on an assistant message that drafted an agent action — the UI
    # fetches GET /ai/actions/{action_id} to re-render its confirm card with
    # the current status when the conversation is reopened.
    action_id: uuid.UUID | None = None
    created_at: datetime


class ConversationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationSummary(ConversationPublic):
    """ConversationPublic plus a short preview of the last message, for the
    conversation list — not from_attributes since the preview isn't a
    column on Conversation itself (see OrchestratorService.list_conversations())."""

    model_config = ConfigDict(from_attributes=False)

    last_message_preview: str | None
