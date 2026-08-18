"""Data-access layer for FXQuote."""
import uuid

from sqlalchemy.orm import Session

from app.fx.models import FXQuote


class FXQuoteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, quote_id: uuid.UUID) -> FXQuote | None:
        return self.db.get(FXQuote, quote_id)

    def add(self, quote: FXQuote) -> FXQuote:
        self.db.add(quote)
        self.db.flush()
        return quote
