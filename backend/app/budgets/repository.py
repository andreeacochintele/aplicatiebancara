"""Data-access layer for Budget, plus the spend-tracking query against Transaction."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.budgets.models import Budget
from app.supabase import is_supabase_session
from app.transactions.models import Transaction, TransactionStatus, TransactionType


class BudgetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, budget: Budget) -> Budget:
        if is_supabase_session(self.db):
            return self.db.add(budget)
        self.db.add(budget)
        self.db.flush()
        return budget

    def get_by_id(self, budget_id: uuid.UUID) -> Budget | None:
        if is_supabase_session(self.db):
            return self.db.get(Budget, budget_id)
        return self.db.get(Budget, budget_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[Budget]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(Budget, {"user_id": f"eq.{user_id}", "order": "created_at.desc"})
        return list(self.db.scalars(select(Budget).where(Budget.user_id == user_id)))

    def spent_amount(
        self,
        user_id: uuid.UUID,
        category_id: uuid.UUID,
        currency: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        """Only COMPLETED, same-currency, real-spend transactions count — a
        budget is denominated in one currency (Budget.currency), and
        CASHBACK is money coming back in, not spend (same exclusion
        AnalyticsRepository._is_real_spend already applies)."""
        if is_supabase_session(self.db):
            rows = self.db.fetch_many(
                Transaction,
                {
                    "initiator_user_id": f"eq.{user_id}",
                    "status": f"eq.{TransactionStatus.COMPLETED.value}",
                    "category_id": f"eq.{category_id}",
                    "currency": f"eq.{currency}",
                },
            )
            return sum(
                (
                    transaction.amount
                    for transaction in rows
                    if period_start <= transaction.created_at <= period_end
                    and transaction.type != TransactionType.CASHBACK
                ),
                Decimal("0"),
            )
        stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.category_id == category_id,
            Transaction.currency == currency,
            Transaction.type != TransactionType.CASHBACK,
            Transaction.created_at >= period_start,
            Transaction.created_at <= period_end,
        )
        return self.db.scalar(stmt) or Decimal("0")
