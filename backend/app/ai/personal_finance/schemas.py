"""Pydantic schemas for AIInsight (see models.py, insights.py)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AIInsightPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: str
    category: str | None
    currency: str | None
    insight_type: str
    dismissed: bool
    created_at: datetime
