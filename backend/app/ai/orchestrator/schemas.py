"""Pydantic schemas for the Orchestrator Agent's chat endpoint."""
from pydantic import BaseModel

from app.ai.orchestrator.intent import IntentCategory


class OrchestratorChatRequest(BaseModel):
    message: str


class OrchestratorChatResponse(BaseModel):
    intent: IntentCategory
    reply: str
    correlation_id: str
