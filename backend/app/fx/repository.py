"""Data-access layer for FXQuote."""
import uuid

from sqlalchemy.orm import Session

from app.fx.models import FXQuote
from app.supabase import is_supabase_session


class FXQuoteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, quote_id: uuid.UUID) -> FXQuote | None:
        if is_supabase_session(self.db):
            return self.db.get(FXQuote, quote_id)
        return self.db.get(FXQuote, quote_id)

    def add(self, quote: FXQuote) -> FXQuote:
        if is_supabase_session(self.db):
            return self.db.add(quote)
        self.db.add(quote)
        self.db.flush()
        return quote
