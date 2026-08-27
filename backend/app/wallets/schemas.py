"""Pydantic schemas for the wallets module."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.wallets.models import WalletStatus


class WalletCreate(BaseModel):
    currency: str
    is_main: bool = False


class WalletPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    currency: str
    iban: str
    available_balance: Decimal
    reserved_balance: Decimal
    is_main: bool
    status: WalletStatus
    created_at: datetime
