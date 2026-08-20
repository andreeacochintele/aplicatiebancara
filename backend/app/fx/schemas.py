"""Pydantic schemas for the fx module."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.fx.models import FXQuoteStatus


class FXQuoteRequest(BaseModel):
    source_currency: str
    target_currency: str
    source_amount: Decimal


class FXMarketRatePublic(BaseModel):
    source_currency: str
    target_currency: str
    rate: Decimal
    fee_rate: Decimal


class FXRatePoint(BaseModel):
    date: str
    rate: Decimal


class FXRateHistoryPublic(BaseModel):
    source_currency: str
    target_currency: str
    points: list[FXRatePoint]


class FXQuotePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_currency: str
    target_currency: str
    source_amount: Decimal
    target_amount: Decimal
    exchange_rate: Decimal
    fee: Decimal
    status: FXQuoteStatus
    expires_at: datetime
    created_at: datetime
