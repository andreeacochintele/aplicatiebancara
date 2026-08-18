"""Pydantic schemas for the rewards module."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.rewards.models import RewardTransactionType


class RewardTransactionPublic(BaseModel):
    id: uuid.UUID
    type: RewardTransactionType
    points: int
    description: str | None
    created_at: datetime


class RewardAccountPublic(BaseModel):
    points_balance: int
    transactions: list[RewardTransactionPublic]


class RewardRedeemRequest(BaseModel):
    points: int
