"""Data-access layer for SavingsGoal."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.savings.models import SavingsGoal
from app.supabase import is_supabase_session


class SavingsGoalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, goal: SavingsGoal) -> SavingsGoal:
        if is_supabase_session(self.db):
            return self.db.add(goal)
        self.db.add(goal)
        self.db.flush()
        return goal

    def get_by_id(self, goal_id: uuid.UUID) -> SavingsGoal | None:
        if is_supabase_session(self.db):
            return self.db.get(SavingsGoal, goal_id)
        return self.db.get(SavingsGoal, goal_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[SavingsGoal]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(SavingsGoal, {"user_id": f"eq.{user_id}", "order": "created_at.desc"})
        return list(self.db.scalars(select(SavingsGoal).where(SavingsGoal.user_id == user_id)))

    def delete(self, goal: SavingsGoal) -> None:
        if is_supabase_session(self.db):
            self.db.delete(goal)
            return
        self.db.delete(goal)
        self.db.flush()
