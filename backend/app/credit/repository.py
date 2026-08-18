"""Data-access layer for credit profiles and score history."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.credit.models import CreditProfile, CreditScoreHistory


class CreditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_profile_by_user(self, user_id: uuid.UUID) -> CreditProfile | None:
        return self.db.scalar(select(CreditProfile).where(CreditProfile.user_id == user_id))

    def add_profile(self, profile: CreditProfile) -> CreditProfile:
        self.db.add(profile)
        self.db.flush()
        return profile

    def add_history(self, history: CreditScoreHistory) -> CreditScoreHistory:
        self.db.add(history)
        self.db.flush()
        return history

    def latest_history(self, profile_id: uuid.UUID) -> CreditScoreHistory | None:
        stmt = (
            select(CreditScoreHistory)
            .where(CreditScoreHistory.credit_profile_id == profile_id)
            .order_by(CreditScoreHistory.created_at.desc())
        )
        return self.db.scalar(stmt)
