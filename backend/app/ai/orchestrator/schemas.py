"""Pydantic schemas for the Orchestrator Agent's chat/conversation endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

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


class ConversationMessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    agent_used: str | None
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
