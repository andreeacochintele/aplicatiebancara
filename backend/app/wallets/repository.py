"""Data-access layer for Wallet."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.wallets.models import Wallet


class WalletRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        if is_supabase_session(self.db):
            return self.db.get(Wallet, wallet_id)
        return self.db.get(Wallet, wallet_id)

    def get_by_user_and_currency(self, user_id: uuid.UUID, currency: str) -> Wallet | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(Wallet, {"user_id": f"eq.{user_id}", "currency": f"eq.{currency}"})
        return self.db.scalar(select(Wallet).where(Wallet.user_id == user_id, Wallet.currency == currency))

    def list_for_user(self, user_id: uuid.UUID) -> list[Wallet]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(Wallet, {"user_id": f"eq.{user_id}", "order": "created_at.asc"})
        return list(self.db.scalars(select(Wallet).where(Wallet.user_id == user_id)))

    def add(self, wallet: Wallet) -> Wallet:
        if is_supabase_session(self.db):
            return self.db.add(wallet)
        self.db.add(wallet)
        self.db.flush()
        return wallet
