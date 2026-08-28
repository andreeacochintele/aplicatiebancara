"""Data-access layer for Card."""
import json
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cards.models import Card, CardPaymentPreferences, CreditCardAccount
from app.supabase import is_supabase_session


CARD_PIN_FALLBACK_PATH = Path(__file__).resolve().parents[2] / ".card_pin_hashes.json"


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

    def update_pin_hash(self, card: Card, pin_hash: str) -> None:
        card.pin_hash = pin_hash
        if is_supabase_session(self.db):
            try:
                rows = self.db.request(
                    "PATCH",
                    Card.__tablename__,
                    params={"id": f"eq.{card.id}"},
                    body={"pin_hash": pin_hash},
                    prefer="return=representation",
                )
            except RuntimeError as exc:
                if "cards.pin_hash does not exist" not in str(exc) and "Could not find the 'pin_hash' column" not in str(exc):
                    raise
                self._write_fallback_pin_hash(card.id, pin_hash)
            else:
                if not isinstance(rows, list) or not rows or rows[0].get("pin_hash") != pin_hash:
                    raise RuntimeError("Card PIN update did not persist")
            self.db._track(card)
            return
        self.db.flush()

    def get_pin_hash(self, card: Card) -> str | None:
        if card.pin_hash:
            return card.pin_hash
        if is_supabase_session(self.db):
            return self._read_fallback_pin_hash(card.id)
        return None

    def _read_fallback_pin_hash(self, card_id: uuid.UUID) -> str | None:
        return self._read_fallback_pin_hashes().get(str(card_id))

    def _write_fallback_pin_hash(self, card_id: uuid.UUID, pin_hash: str) -> None:
        data = self._read_fallback_pin_hashes()
        data[str(card_id)] = pin_hash
        CARD_PIN_FALLBACK_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _read_fallback_pin_hashes(self) -> dict[str, str]:
        if not CARD_PIN_FALLBACK_PATH.exists():
            return {}
        try:
            payload = json.loads(CARD_PIN_FALLBACK_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if isinstance(value, str)}

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
