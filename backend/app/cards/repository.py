"""Data-access layer for Card."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cards.models import Card, CardPaymentPreferences


class CardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, card_id: uuid.UUID) -> Card | None:
        return self.db.get(Card, card_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[Card]:
        stmt = select(Card).where(Card.user_id == user_id).order_by(Card.created_at.desc())
        return list(self.db.scalars(stmt))

    def add(self, card: Card) -> Card:
        self.db.add(card)
        self.db.flush()
        return card

    def get_preferences(self, card_id: uuid.UUID) -> CardPaymentPreferences | None:
        return self.db.get(CardPaymentPreferences, card_id)

    def add_preferences(self, preferences: CardPaymentPreferences) -> CardPaymentPreferences:
        self.db.add(preferences)
        self.db.flush()
        return preferences
