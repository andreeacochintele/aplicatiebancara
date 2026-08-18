"""Pydantic schemas for the credit module."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class CreditProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    current_score: int
    income: Decimal
    existing_debt: Decimal
    updated_at: datetime


class CreditScoreRecalculateRequest(BaseModel):
    income: Decimal | None = None
    existing_debt: Decimal | None = None


class CreditScorePublic(BaseModel):
    score: int
    band: str
    reason_data: dict[str, Any]
    calculated_at: datetime
