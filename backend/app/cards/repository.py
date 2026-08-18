"""Data-access layer for Card."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cards.models import Card


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
