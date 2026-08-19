"""Pydantic schemas for the merchants module."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.merchants.models import CashbackOfferStatus, MerchantStatus


class MerchantCreate(BaseModel):
    name: str
    category: str
    logo_url: str | None = None
    verified: bool = False


class CashbackOfferCreate(BaseModel):
    cashback_percent: Decimal
    maximum_cashback: Decimal | None = None
    minimum_spend: Decimal | None = None
    start_date: date
    end_date: date


class CashbackOfferPublic(BaseModel):
    id: uuid.UUID
    cashback_percent: Decimal
    maximum_cashback: Decimal | None
    minimum_spend: Decimal | None
    start_date: date
    end_date: date
    status: CashbackOfferStatus


class MerchantPublic(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    logo_url: str | None
    status: MerchantStatus
    verified: bool
    active_offer: CashbackOfferPublic | None
    created_at: datetime


class PurchaseResult(BaseModel):
    merchant_id: uuid.UUID
    amount: Decimal
    currency: str
    cashback_percent: Decimal | None
    cashback_amount: Decimal
    points_earned: int
    reward_points_balance: int
