"""Savings goal endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.savings.schemas import SavingsContribution, SavingsGoalCreate, SavingsGoalPublic
from app.savings.service import SavingsService
from app.users.models import User

router = APIRouter(prefix="/savings", tags=["savings"])


@router.get("", response_model=list[SavingsGoalPublic])
def list_my_savings_goals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavingsGoalPublic]:
    return SavingsService(db).list_goals(current_user.id)


@router.post("", response_model=SavingsGoalPublic, status_code=201)
def create_savings_goal(
    payload: SavingsGoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavingsGoalPublic:
    goal = SavingsService(db).create_goal(current_user.id, payload)
    db.commit()
    return goal


@router.post("/{goal_id}/contribute", response_model=SavingsGoalPublic)
def contribute_to_goal(
    goal_id: uuid.UUID,
    payload: SavingsContribution,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavingsGoalPublic:
    goal = SavingsService(db).contribute(current_user.id, goal_id, payload.amount)
    db.commit()
    return goal
