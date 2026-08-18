"""Cards business rules."""
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.cards.models import Card, CardStatus, CardType
from app.cards.repository import CardRepository
from app.cards.schemas import CardCreate
from app.core.exceptions import NotFoundError, ValidationError
from app.wallets.models import WalletStatus
from app.wallets.repository import WalletRepository


class CardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CardRepository(db)
        self.wallets = WalletRepository(db)

    def create_card(self, user_id: uuid.UUID, data: CardCreate) -> Card:
        if data.default_wallet_id is not None:
            wallet = self.wallets.get_by_id(data.default_wallet_id)
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Default wallet not found")
            if wallet.status != WalletStatus.ACTIVE:
                raise ValidationError("Default wallet must be active")

        last_four = f"{secrets.randbelow(10000):04d}"
        now = datetime.now(timezone.utc)
        one_time_remaining = 1 if data.type == CardType.ONE_TIME else None

        card = Card(
            user_id=user_id,
            default_wallet_id=data.default_wallet_id,
            type=data.type,
            status=CardStatus.ACTIVE,
            masked_pan=f"**** **** **** {last_four}",
            last_four=last_four,
            expiration_month=now.month,
            expiration_year=now.year + 4,
            one_time_remaining=one_time_remaining,
        )
        return self.repository.add(card)

    def list_cards(self, user_id: uuid.UUID) -> list[Card]:
        return self.repository.list_for_user(user_id)

    def get_for_user(self, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
        card = self.repository.get_by_id(card_id)
        if card is None or card.user_id != user_id:
            raise NotFoundError("Card not found")
        return card

    def freeze_card(self, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
        card = self.get_for_user(user_id, card_id)
        if card.status == CardStatus.FROZEN:
            return card
        if card.status != CardStatus.ACTIVE:
            raise ValidationError("Only active cards can be frozen")
        card.status = CardStatus.FROZEN
        self.db.flush()
        return card

    def unfreeze_card(self, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
        card = self.get_for_user(user_id, card_id)
        if card.status == CardStatus.ACTIVE:
            return card
        if card.status != CardStatus.FROZEN:
            raise ValidationError("Only frozen cards can be unfrozen")
        card.status = CardStatus.ACTIVE
        self.db.flush()
        return card
