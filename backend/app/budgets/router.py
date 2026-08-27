"""Budget endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.budgets.schemas import BudgetCreate, BudgetPublic
from app.budgets.service import BudgetService
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetPublic])
def list_my_budgets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BudgetPublic]:
    return BudgetService(db).list_budgets(current_user.id)


@router.post("", response_model=BudgetPublic, status_code=201)
def create_budget(
    payload: BudgetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetPublic:
    budget = BudgetService(db).create_budget(current_user.id, payload)
    db.commit()
    return budget


@router.delete("/{budget_id}", status_code=204)
def delete_budget(
    budget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    BudgetService(db).delete_budget(current_user.id, budget_id)
    db.commit()
