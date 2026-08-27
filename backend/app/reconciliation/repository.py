"""Data-access layer for wallet-ledger reconciliation — reads every wallet
and, for each, every ledger entry ever written against it (no date bound,
unlike statements/repository.py's period-scoped query)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.transactions.models import WalletLedgerEntry
from app.wallets.models import Wallet


class ReconciliationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all_wallets(self) -> list[Wallet]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(Wallet, {"order": "created_at.asc"})
        return list(self.db.scalars(select(Wallet).order_by(Wallet.created_at)))

    def list_all_entries_for_wallet(self, wallet_id) -> list[WalletLedgerEntry]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(WalletLedgerEntry, {"wallet_id": f"eq.{wallet_id}"})
        return list(self.db.scalars(select(WalletLedgerEntry).where(WalletLedgerEntry.wallet_id == wallet_id)))
