"""HTTP layer for the Orchestrator Agent — no business logic here."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError
from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.orchestrator.schemas import OrchestratorChatRequest, OrchestratorChatResponse
from app.ai.orchestrator.service import OrchestratorService
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
        response = OrchestratorService(db).chat(current_user.id, payload.message)
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
