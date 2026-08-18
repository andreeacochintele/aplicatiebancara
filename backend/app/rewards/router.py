"""Reward points endpoints, scoped to the authenticated user (architecture.md §11)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.rewards.schemas import RewardAccountPublic, RewardRedeemRequest
from app.rewards.service import RewardsService
from app.users.models import User

router = APIRouter(prefix="/rewards", tags=["rewards"])


@router.get("", response_model=RewardAccountPublic)
def get_my_rewards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RewardAccountPublic:
    return RewardsService(db).get_account(current_user.id)


@router.post("/redeem", response_model=RewardAccountPublic)
def redeem_points(
    payload: RewardRedeemRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RewardAccountPublic:
    result = RewardsService(db).redeem_points(current_user.id, payload.points)
    db.commit()
    return result
