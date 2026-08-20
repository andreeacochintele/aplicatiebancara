"""Cards business rules."""
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.cards.models import Card, CardPaymentPreferences, CardStatus, CardTier, CardType
from app.cards.repository import CardRepository
from app.cards.schemas import CardCreate, CardPaymentPreferencesUpdate
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.wallets.models import WalletStatus
from app.wallets.repository import WalletRepository


class CardService:
    MAX_CARDS_PER_USER = 5

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CardRepository(db)
        self.wallets = WalletRepository(db)

    def create_card(self, user_id: uuid.UUID, data: CardCreate) -> Card:
        existing_cards = self.repository.list_for_user(user_id)
        if len(existing_cards) >= self.MAX_CARDS_PER_USER:
            raise ConflictError("Card limit reached. You can have up to 5 cards.")

        if data.type == CardType.ONE_TIME and data.tier is not None:
            raise ValidationError("One-time cards do not have tiers")

        if data.type in (CardType.DEBIT, CardType.ONE_TIME) and data.default_wallet_id is None:
            raise ValidationError("Debit and one-time cards must be linked to an account")

        if data.default_wallet_id is not None:
            wallet = self.wallets.get_by_id(data.default_wallet_id)
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Default wallet not found")
            if wallet.status != WalletStatus.ACTIVE:
                raise ValidationError("Default wallet must be active")

        if data.type == CardType.DEBIT and data.default_wallet_id is not None:
            for existing_card in existing_cards:
                if existing_card.type == CardType.DEBIT and existing_card.default_wallet_id == data.default_wallet_id:
                    raise ConflictError("This account already has a debit card")

        if data.type == CardType.ONE_TIME:
            for existing_card in existing_cards:
                if existing_card.type == CardType.ONE_TIME and existing_card.status in (CardStatus.ACTIVE, CardStatus.FROZEN):
                    raise ConflictError("You can only have one one-time payment card")

        default_wallet_id = data.default_wallet_id if data.type in (CardType.DEBIT, CardType.ONE_TIME) else None
        last_four = f"{secrets.randbelow(10000):04d}"
        mock_pan = f"4000 {secrets.randbelow(10000):04d} {secrets.randbelow(10000):04d} {last_four}"
        mock_cvv = f"{secrets.randbelow(1000):03d}"
        now = datetime.now(timezone.utc)
        one_time_remaining = 1 if data.type == CardType.ONE_TIME else None
        tier = None if data.type == CardType.ONE_TIME else data.tier or CardTier.REGULAR

        card = Card(
            user_id=user_id,
            default_wallet_id=default_wallet_id,
            type=data.type,
            tier=tier,
            status=CardStatus.ACTIVE,
            masked_pan=f"**** **** **** {last_four}",
            last_four=last_four,
            mock_pan=mock_pan,
            mock_cvv=mock_cvv,
            expiration_month=now.month,
            expiration_year=now.year + 4,
            one_time_remaining=one_time_remaining,
        )
        card = self.repository.add(card)
        self.repository.add_preferences(
            CardPaymentPreferences(card_id=card.id, preferred_wallet_id=default_wallet_id)
        )
        return card

    def list_cards(self, user_id: uuid.UUID) -> list[Card]:
        return self.repository.list_for_user(user_id)

    def get_for_user(self, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
        card = self.repository.get_by_id(card_id)
        if card is None or card.user_id != user_id:
            raise NotFoundError("Card not found")
        return card

    def delete_card(self, user_id: uuid.UUID, card_id: uuid.UUID) -> None:
        card = self.get_for_user(user_id, card_id)
        self.repository.delete(card)

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

    def get_payment_preferences(self, user_id: uuid.UUID, card_id: uuid.UUID) -> CardPaymentPreferences:
        card = self.get_for_user(user_id, card_id)
        preferences = self.repository.get_preferences(card.id)
        if preferences is None:
            preferences = self.repository.add_preferences(CardPaymentPreferences(card_id=card.id))
        return preferences

    def update_payment_preferences(
        self,
        user_id: uuid.UUID,
        card_id: uuid.UUID,
        data: CardPaymentPreferencesUpdate,
    ) -> CardPaymentPreferences:
        card = self.get_for_user(user_id, card_id)
        if data.preferred_wallet_id is not None:
            wallet = self.wallets.get_by_id(data.preferred_wallet_id)
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Preferred wallet not found")
            if wallet.status != WalletStatus.ACTIVE:
                raise ValidationError("Preferred wallet must be active")

        preferences = self.repository.get_preferences(card.id)
        if preferences is None:
            preferences = self.repository.add_preferences(CardPaymentPreferences(card_id=card.id))

        preferences.preferred_wallet_id = data.preferred_wallet_id
        preferences.allow_main_wallet_fx = data.allow_main_wallet_fx
        self.db.flush()
        return preferences
