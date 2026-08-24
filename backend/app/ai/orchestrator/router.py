"""HTTP layer for the Orchestrator Agent — no business logic here."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.orchestrator.schemas import OrchestratorChatRequest, OrchestratorChatResponse
from app.ai.orchestrator.service import OrchestratorService
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/ai/orchestrator", tags=["ai-orchestrator"])


@router.post("/chat", response_model=OrchestratorChatResponse)
def chat(
    payload: OrchestratorChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrchestratorChatResponse:
    try:
        return OrchestratorService(db).chat(current_user.id, payload.message)
    except AzureFoundryNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
