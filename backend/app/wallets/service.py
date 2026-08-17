"""Wallet business rules: one wallet per currency per user, exactly one main wallet."""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository
from app.wallets.schemas import WalletCreate


class WalletService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = WalletRepository(db)

    def create_wallet(self, user_id: uuid.UUID, data: WalletCreate) -> Wallet:
        currency = data.currency.upper()
        if self.repository.get_by_user_and_currency(user_id, currency):
            raise ConflictError(f"Wallet for currency '{currency}' already exists")

        make_main = data.is_main
        if make_main:
            for existing in self.repository.list_for_user(user_id):
                existing.is_main = False
        elif not self.repository.list_for_user(user_id):
            # first wallet for a user is automatically the main wallet
            make_main = True

        wallet = Wallet(user_id=user_id, currency=currency, is_main=make_main)
        return self.repository.add(wallet)

    def list_wallets(self, user_id: uuid.UUID) -> list[Wallet]:
        return self.repository.list_for_user(user_id)
