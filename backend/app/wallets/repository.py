"""Data-access layer for Wallet."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.wallets.models import Wallet, WalletStatus


class WalletRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        if is_supabase_session(self.db):
            return self.db.get(Wallet, wallet_id)
        return self.db.get(Wallet, wallet_id)

    def get_by_id_for_update(self, wallet_id: uuid.UUID) -> Wallet | None:
        """Same as get_by_id, but locks the row (SELECT ... FOR UPDATE) for
        the rest of the transaction — use this instead of get_by_id anywhere
        a wallet's balance is read and then mutated, so two concurrent
        requests against the same wallet serialize instead of both reading
        the pre-mutation balance and both passing an insufficient-funds
        check. PostgREST (the Supabase REST backend) has no row-locking
        primitive, so that branch is best-effort only, same as it already
        is for every other concurrency concern in that backend."""
        if is_supabase_session(self.db):
            return self.db.get(Wallet, wallet_id)
        return self.db.scalar(select(Wallet).where(Wallet.id == wallet_id).with_for_update())

    def get_by_user_and_currency(self, user_id: uuid.UUID, currency: str) -> Wallet | None:
        """A user can hold more than one wallet in the same currency (see
        wallets/models.py), so this picks one deterministically for callers
        that need "the" wallet for a currency (credit disbursement, an
        incoming phone transfer, a bill-split payout): preferring an ACTIVE
        one (the user's overall main wallet first, else the oldest), but
        still falling back to a non-active one rather than None when that's
        all that exists — callers rely on getting back a FROZEN/CLOSED
        wallet so they can react to that specific status (see
        credit/service.py's _get_or_create_disbursement_wallet) rather than
        treating "not active" the same as "doesn't exist"."""

        def _sort_key(wallet: Wallet) -> tuple[bool, bool, datetime]:
            # SQLite (tests) drops tzinfo on round-trip even for
            # DateTime(timezone=True) columns; Postgres preserves it.
            # Normalize so this comparison works on both.
            created_at = wallet.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            return (wallet.status != WalletStatus.ACTIVE, not wallet.is_main, created_at)

        if is_supabase_session(self.db):
            candidates = self.db.fetch_many(Wallet, {"user_id": f"eq.{user_id}", "currency": f"eq.{currency}"})
            return min(candidates, key=_sort_key) if candidates else None
        candidates = list(
            self.db.scalars(select(Wallet).where(Wallet.user_id == user_id, Wallet.currency == currency))
        )
        return min(candidates, key=_sort_key) if candidates else None

    def get_by_iban(self, iban: str) -> Wallet | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(Wallet, {"iban": f"eq.{iban}"})
        return self.db.scalar(select(Wallet).where(Wallet.iban == iban))

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
