"""Data-access layer for SavingsGoal."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.savings.models import SavingsGoal


class SavingsGoalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, goal: SavingsGoal) -> SavingsGoal:
        self.db.add(goal)
        self.db.flush()
        return goal

    def get_by_id(self, goal_id: uuid.UUID) -> SavingsGoal | None:
        return self.db.get(SavingsGoal, goal_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[SavingsGoal]:
        return list(self.db.scalars(select(SavingsGoal).where(SavingsGoal.user_id == user_id)))
