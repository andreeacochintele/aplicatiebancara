"""Admin fraud review endpoints (architecture.md §32).

The Fraud Investigation Agent's POST /fraud/cases/{id}/investigate isn't
added yet — it belongs with the rest of ai/* on feature/dev4/ai-agents,
which doesn't exist yet either. Cases are scored and held automatically by
FraudService.evaluate_transaction (called from
TransactionService.create_card_payment); an admin only ever approves or
rejects an already-created case here.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

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
