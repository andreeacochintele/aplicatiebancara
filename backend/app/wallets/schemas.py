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
    # Optional: the live app runs on Supabase REST, and the iban column/backfill
    # (supabase/sql/supabase_add_wallet_iban.sql) hasn't been applied there yet.
    # Until it is, Supabase returns no iban for existing rows — a required str
    # here would 500 every GET /wallets response instead of just omitting it.
    iban: str | None = None
    available_balance: Decimal
    reserved_balance: Decimal
    is_main: bool
    status: WalletStatus
    created_at: datetime
