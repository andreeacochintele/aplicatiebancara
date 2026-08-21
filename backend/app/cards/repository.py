"""Data-access layer for Card."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cards.models import Card, CardPaymentPreferences, CreditCardAccount
from app.supabase import is_supabase_session


class CardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, card_id: uuid.UUID) -> Card | None:
        if is_supabase_session(self.db):
            return self.db.get(Card, card_id)
        return self.db.get(Card, card_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[Card]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(Card, {"user_id": f"eq.{user_id}", "order": "created_at.desc"})
        stmt = select(Card).where(Card.user_id == user_id).order_by(Card.created_at.desc())
        return list(self.db.scalars(stmt))

    def add(self, card: Card) -> Card:
        if is_supabase_session(self.db):
            return self.db.add(card)
        self.db.add(card)
        self.db.flush()
        return card

    def delete(self, card: Card) -> None:
        preferences = self.get_preferences(card.id)
        if preferences is not None:
            self.db.delete(preferences)
        credit_account = self.get_credit_account(card.id)
        if credit_account is not None:
            self.db.delete(credit_account)
        self.db.delete(card)
        self.db.flush()

    def get_preferences(self, card_id: uuid.UUID) -> CardPaymentPreferences | None:
        if is_supabase_session(self.db):
            return self.db.get(CardPaymentPreferences, card_id)
        return self.db.get(CardPaymentPreferences, card_id)

    def add_preferences(self, preferences: CardPaymentPreferences) -> CardPaymentPreferences:
        if is_supabase_session(self.db):
            return self.db.add(preferences)
        self.db.add(preferences)
        self.db.flush()
        return preferences

    def get_credit_account(self, card_id: uuid.UUID) -> CreditCardAccount | None:
        if is_supabase_session(self.db):
            return self.db.get(CreditCardAccount, card_id)
        return self.db.get(CreditCardAccount, card_id)

    def add_credit_account(self, account: CreditCardAccount) -> CreditCardAccount:
        if is_supabase_session(self.db):
            return self.db.add(account)
        self.db.add(account)
        self.db.flush()
        return account
