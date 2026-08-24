"""Orchestrator business logic: classify intent, then either answer directly
(greeting / out_of_scope) or route to the matching specialized agent stub.
"""
import uuid

from sqlalchemy.orm import Session

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
        intent = classify_intent(message)

        if intent == IntentCategory.GREETING:
            return OrchestratorChatResponse(intent=intent, reply=_GREETING_REPLY)
        if intent == IntentCategory.OUT_OF_SCOPE:
            return OrchestratorChatResponse(intent=intent, reply=_OUT_OF_SCOPE_REPLY)

        agent_handle = AGENT_REGISTRY[intent]
        reply = agent_handle(message, user_id, self.db)
        return OrchestratorChatResponse(intent=intent, reply=reply)
