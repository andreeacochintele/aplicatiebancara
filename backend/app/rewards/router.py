"""Reward points, tier and benefits-catalog endpoints, scoped to the authenticated user
(architecture.md §11)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.rewards.schemas import (
    BenefitRedeemRequest,
    RewardAccountPublic,
    RewardBenefitPublic,
    RewardRedeemRequest,
)
from app.rewards.service import RewardsService
from app.users.models import User

router = APIRouter(prefix="/rewards", tags=["rewards"])


@router.get("", response_model=RewardAccountPublic)
def get_my_rewards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RewardAccountPublic:
    # get_account() can backfill a missing referral_code as a side effect
    # (RewardsService.get_or_create_account) — must commit or the generated
    # code never persists and a different one gets generated on every call.
    result = RewardsService(db).get_account(current_user.id)
    db.commit()
    return result


@router.post("/redeem", response_model=RewardAccountPublic)
def redeem_points(
    payload: RewardRedeemRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RewardAccountPublic:
    result = RewardsService(db).redeem_points(current_user.id, payload.points)
    db.commit()
    return result


@router.get("/benefits", response_model=list[RewardBenefitPublic])
def list_benefits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RewardBenefitPublic]:
    return RewardsService(db).list_benefits(current_user.id)


@router.post("/benefits/{benefit_id}/redeem", response_model=RewardAccountPublic)
def redeem_benefit(
    benefit_id: uuid.UUID,
    payload: BenefitRedeemRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RewardAccountPublic:
    result = RewardsService(db).redeem_benefit(current_user.id, benefit_id, payload.card_id)
    db.commit()
    return result


@router.post("/redemptions/{redemption_id}/use", response_model=RewardAccountPublic)
def mark_redemption_used(
    redemption_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RewardAccountPublic:
    result = RewardsService(db).mark_redemption_used(current_user.id, redemption_id)
    db.commit()
    return result
