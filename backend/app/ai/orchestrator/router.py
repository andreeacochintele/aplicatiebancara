"""HTTP layer for the Orchestrator Agent — no business logic here.

The old flat GET /history (all messages for a user, unscoped) was replaced
by the three conversation-aware endpoints below rather than kept as a
backward-compat wrapper: it had shipped in this same working session with
no other consumer yet (frontend included, updated in the same change), so
there was nothing to actually stay compatible with, and a route whose
semantics silently changed from "everything" to "one conversation" would
be more confusing than just removing it.
"""
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError
from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.orchestrator.schemas import (
    ConversationMessagePublic,
    ConversationPublic,
    ConversationSummary,
    OrchestratorChatRequest,
    OrchestratorChatResponse,
)
from app.ai.orchestrator.service import MESSAGES_PAGE_LIMIT, OrchestratorService
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/orchestrator", tags=["ai-orchestrator"])


@router.post("/chat", response_model=OrchestratorChatResponse)
def chat(
    payload: OrchestratorChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrchestratorChatResponse:
    try:
        response = OrchestratorService(db).chat(current_user.id, payload.message, payload.conversation_id)
        db.commit()
        return response
    except AzureFoundryNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except APIError as exc:
        # Credentials configured but the call itself failed (wrong deployment
        # name, auth rejected, rate limited, Azure-side outage, ...) — don't
        # leak Azure's raw error/endpoint details to the client.
        logger.exception("Azure AI Foundry request failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI assistant is temporarily unavailable. Please try again later.",
        ) from exc


@router.post("/conversations", response_model=ConversationPublic, status_code=status.HTTP_201_CREATED)
def create_conversation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationPublic:
    conversation = OrchestratorService(db).create_conversation(current_user.id)
    db.commit()
    return ConversationPublic.model_validate(conversation)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    return OrchestratorService(db).list_conversations(current_user.id, limit=limit)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ConversationMessagePublic])
def get_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int = MESSAGES_PAGE_LIMIT,
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationMessagePublic]:
    """Chronological page of this conversation's messages — the most recent
    page by default, or the page immediately before `before` (an ISO
    timestamp) for loading older messages on scroll-up."""
    messages = OrchestratorService(db).get_conversation_messages(
        current_user.id, conversation_id, limit=limit, before=before
    )
    return [ConversationMessagePublic.model_validate(message) for message in messages]
