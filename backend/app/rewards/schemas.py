"""Pydantic schemas for the rewards module."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.cards.models import CardTier
from app.rewards.models import BenefitCategory, RedemptionStatus, RewardTransactionType


class RewardTransactionPublic(BaseModel):
    id: uuid.UUID
    type: RewardTransactionType
    points: int
    description: str | None
    proof_code: str | None
    created_at: datetime


class RewardBenefitPublic(BaseModel):
    id: uuid.UUID
    name: str
    category: BenefitCategory
    description: str
    points_cost: int | None
    min_card_tier: CardTier | None
    partner_name: str | None
    can_redeem: bool
    reason_if_locked: str | None


class BenefitRedemptionPublic(BaseModel):
    id: uuid.UUID
    benefit_id: uuid.UUID
    benefit_name: str
    card_id: uuid.UUID | None
    redemption_code: str | None
    points_spent: int
    redeemed_at: datetime
    expires_at: datetime | None
    used_at: datetime | None
    status: RedemptionStatus


class RewardAccountPublic(BaseModel):
    points_balance: int
    lifetime_points_earned: int
    referral_code: str | None
    transactions: list[RewardTransactionPublic]
    redemptions: list[BenefitRedemptionPublic]


class RewardRedeemRequest(BaseModel):
    points: int


class BenefitRedeemRequest(BaseModel):
    card_id: uuid.UUID
