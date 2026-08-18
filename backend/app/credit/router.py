"""Credit endpoints, scoped to the authenticated user."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.credit.schemas import CreditProfilePublic, CreditScorePublic, CreditScoreRecalculateRequest
from app.credit.service import CreditService
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/credit", tags=["credit"])


@router.get("/profile", response_model=CreditProfilePublic)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditProfilePublic:
    profile = CreditService(db).get_or_create_profile(current_user.id)
    db.commit()
    return profile


@router.get("/score", response_model=CreditScorePublic)
def get_score(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditScorePublic:
    score = CreditService(db).get_score(current_user.id)
    db.commit()
    return score


@router.post("/score/recalculate", response_model=CreditScorePublic)
def recalculate_score(
    payload: CreditScoreRecalculateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditScorePublic:
    score = CreditService(db).recalculate_score(current_user.id, payload)
    db.commit()
    return score
