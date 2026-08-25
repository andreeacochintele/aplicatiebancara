"""Admin fraud review endpoints (architecture.md §32).

Cases are scored and held automatically by FraudService.evaluate_transaction
(called from TransactionService.create_card_payment); an admin approves or
rejects an already-created case via /decision below — the Fraud
Investigation Agent (ai/fraud/agent.py, triggered by /investigate) never
makes or overrides that decision, it only adds an advisory qualitative
read the admin can see alongside the unchanged deterministic risk_score.
/investigate is on-demand only — nothing here calls it automatically when a
case is created.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.fraud import agent as fraud_investigation_agent
from app.auth.dependencies import require_admin
from app.database import get_db
from app.fraud.schemas import FraudCaseDetail, FraudCaseSummary, FraudDecisionRequest
from app.fraud.service import FraudService
from app.users.models import User

router = APIRouter(prefix="/fraud", tags=["fraud"])


@router.get("/cases", response_model=list[FraudCaseSummary])
def list_fraud_cases(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[FraudCaseSummary]:
    return FraudService(db).list_pending()


@router.get("/cases/{case_id}", response_model=FraudCaseDetail)
def get_fraud_case(
    case_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FraudCaseDetail:
    service = FraudService(db)
    case = service.get_case(case_id)
    return service.to_detail(case)


@router.post("/cases/{case_id}/decision", response_model=FraudCaseDetail)
def decide_fraud_case(
    case_id: uuid.UUID,
    payload: FraudDecisionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FraudCaseDetail:
    service = FraudService(db)
    case = service.get_case(case_id)
    if payload.action == "APPROVE":
        case = service.approve(case, admin)
    else:
        case = service.reject(case, admin)
    db.commit()
    return service.to_detail(case)


@router.post("/cases/{case_id}/investigate", response_model=FraudCaseDetail)
def investigate_fraud_case(
    case_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FraudCaseDetail:
    """Runs the Fraud Investigation Agent for this case on demand and caches
    its output on the case (FraudCase.agent_analysis) — never runs
    automatically, never touches risk_score/status/the APPROVE-REJECT
    decision. GET /cases/{case_id} returns whatever's cached here without
    re-running the agent."""
    service = FraudService(db)
    case = service.get_case(case_id)
    result = fraud_investigation_agent.investigate(case_id, db)
    service.save_agent_analysis(case, result.risk_level, result.explanation, **result.analysis_sections())
    db.commit()
    return service.to_detail(case)
