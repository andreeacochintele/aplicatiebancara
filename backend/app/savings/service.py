"""Savings goal business rules."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.savings.models import SavingsGoal
from app.savings.repository import SavingsGoalRepository
from app.savings.schemas import SavingsGoalCreate, SavingsGoalPublic


class SavingsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = SavingsGoalRepository(db)

    def create_goal(self, user_id: uuid.UUID, data: SavingsGoalCreate) -> SavingsGoalPublic:
        if data.target_amount <= 0:
            raise ValidationError("target_amount must be positive")
        if data.initial_amount < 0:
            raise ValidationError("initial_amount cannot be negative")

        goal = SavingsGoal(
            user_id=user_id,
            name=data.name,
            target_amount=data.target_amount,
            current_amount=data.initial_amount,
            currency=data.currency.upper(),
            target_date=data.target_date,
        )
        self.repository.add(goal)
        return self._to_public(goal)

    def list_goals(self, user_id: uuid.UUID) -> list[SavingsGoalPublic]:
        return [self._to_public(goal) for goal in self.repository.list_for_user(user_id)]

    def contribute(self, user_id: uuid.UUID, goal_id: uuid.UUID, amount: Decimal) -> SavingsGoalPublic:
        if amount <= 0:
            raise ValidationError("amount must be positive")

        goal = self.repository.get_by_id(goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFoundError("Savings goal not found")

        goal.current_amount += amount
        self.db.flush()
        return self._to_public(goal)

    def _to_public(self, goal: SavingsGoal) -> SavingsGoalPublic:
        percent_complete = (
            round(float(goal.current_amount / goal.target_amount) * 100, 1) if goal.target_amount else 0.0
        )
        remaining = goal.target_amount - goal.current_amount
        monthly_needed = None
        if goal.target_date is not None and remaining > 0:
            months = self._months_between(datetime.now(timezone.utc).date(), goal.target_date)
            monthly_needed = (remaining / months).quantize(Decimal("0.01"))

        return SavingsGoalPublic(
            id=goal.id,
            name=goal.name,
            target_amount=goal.target_amount,
            current_amount=goal.current_amount,
            currency=goal.currency,
            target_date=goal.target_date,
            percent_complete=percent_complete,
            monthly_amount_needed=monthly_needed,
            created_at=goal.created_at,
        )

    @staticmethod
    def _months_between(today: date, target: date) -> int:
        months = (target.year - today.year) * 12 + (target.month - today.month)
        return max(months, 1)
