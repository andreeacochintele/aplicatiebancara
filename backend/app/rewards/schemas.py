"""Pydantic schemas for the rewards module."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.rewards.models import BenefitCategory, RewardTransactionType


class RewardTransactionPublic(BaseModel):
    id: uuid.UUID
    type: RewardTransactionType
    points: int
    description: str | None
    created_at: datetime


class RewardTierPublic(BaseModel):
    id: uuid.UUID
    name: str
    min_lifetime_points: int
    perks: list[str]


class RewardBenefitPublic(BaseModel):
    id: uuid.UUID
    name: str
    category: BenefitCategory
    description: str
    points_cost: int | None
    min_tier: RewardTierPublic | None
    partner_name: str | None
    can_redeem: bool
    reason_if_locked: str | None


class BenefitRedemptionPublic(BaseModel):
    id: uuid.UUID
    benefit_id: uuid.UUID
    benefit_name: str
    points_spent: int
    redeemed_at: datetime


class RewardAccountPublic(BaseModel):
    points_balance: int
    lifetime_points_earned: int
    tier: RewardTierPublic
    tier_boosted_by_card: bool
    next_tier: RewardTierPublic | None
    points_to_next_tier: int | None
    transactions: list[RewardTransactionPublic]
    redemptions: list[BenefitRedemptionPublic]


class RewardRedeemRequest(BaseModel):
    points: int
