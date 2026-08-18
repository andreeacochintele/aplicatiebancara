"""Data-access layer for Budget, plus the spend-tracking query against Transaction."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.budgets.models import Budget
from app.transactions.models import Transaction, TransactionStatus


class BudgetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, budget: Budget) -> Budget:
        self.db.add(budget)
        self.db.flush()
        return budget

    def get_by_id(self, budget_id: uuid.UUID) -> Budget | None:
        return self.db.get(Budget, budget_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[Budget]:
        return list(self.db.scalars(select(Budget).where(Budget.user_id == user_id)))

    def spent_amount(
        self, user_id: uuid.UUID, category_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.category_id == category_id,
            Transaction.created_at >= period_start,
            Transaction.created_at <= period_end,
        )
        return self.db.scalar(stmt) or Decimal("0")
