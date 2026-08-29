"""Data-access layer for Budget, plus the spend-tracking query against Transaction."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.budgets.models import Budget
from app.merchants.models import Merchant
from app.supabase import is_supabase_session
from app.transactions.categories import (
    effective_category_column,
    join_category_sources,
    resolve_effective_category,
)
from app.transactions.models import Transaction, TransactionCategory, TransactionStatus, TransactionType


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

    def delete(self, budget: Budget) -> None:
        if is_supabase_session(self.db):
            self.db.delete(budget)
            return
        self.db.delete(budget)
        self.db.flush()

    def spent_amount(
        self,
        user_id: uuid.UUID,
        category: str,
        currency: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        """Card payments in this category, resolved the same way the
        Analytics donut resolves it (transactions/categories.py): the user's
        own per-transaction choice where they made one, otherwise the paying
        merchant's category. Re-filing a payment therefore moves it between
        budgets exactly as it moves it between donut slices — the two views
        must never report different spend for the same month.

        A budget tracks real purchases, so transfers and loan payments
        (neither is a "purchase" against any category) are excluded outright
        rather than through CASHBACK-style filtering."""
        if is_supabase_session(self.db):
            rows = self.db.fetch_many(
                Transaction,
                {
                    "initiator_user_id": f"eq.{user_id}",
                    "status": f"eq.{TransactionStatus.COMPLETED.value}",
                    "type": f"eq.{TransactionType.CARD_PAYMENT.value}",
                    "currency": f"eq.{currency}",
                },
            )
            merchants_by_id = {m.id: m for m in self.db.fetch_many(Merchant, {})}
            categories_by_id = {c.id: c for c in self.db.fetch_many(TransactionCategory, {})}
            total = Decimal("0")
            for transaction in rows:
                if not (period_start <= transaction.created_at <= period_end):
                    continue
                if resolve_effective_category(transaction, merchants_by_id, categories_by_id) == category:
                    total += transaction.amount
            return total

        stmt = join_category_sources(
            select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(Transaction)
        ).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.type == TransactionType.CARD_PAYMENT,
            Transaction.currency == currency,
            effective_category_column() == category,
            Transaction.created_at >= period_start,
            Transaction.created_at <= period_end,
        )
        return self.db.scalar(stmt) or Decimal("0")
