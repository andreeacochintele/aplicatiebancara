"""Credit endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.credit.schemas import (
    CreditApplicationCreate,
    CreditApplicationPublic,
    CreditProfilePublic,
    CreditScorePublic,
    CreditScoreRecalculateRequest,
    LoanCalculatorRequest,
    LoanCalculatorResult,
)
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


@router.post("/loan-calculator", response_model=LoanCalculatorResult)
def calculate_loan(
    payload: LoanCalculatorRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanCalculatorResult:
    return CreditService(db).calculate_loan(payload)


@router.get("/applications", response_model=list[CreditApplicationPublic])
def list_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CreditApplicationPublic]:
    return CreditService(db).list_applications(current_user.id)


@router.post("/applications", response_model=CreditApplicationPublic, status_code=201)
def create_application(
    payload: CreditApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditApplicationPublic:
    application = CreditService(db).create_application(current_user.id, payload)
    db.commit()
    return application


@router.get("/applications/{application_id}", response_model=CreditApplicationPublic)
def get_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditApplicationPublic:
    return CreditService(db).get_application_for_user(current_user.id, application_id)
