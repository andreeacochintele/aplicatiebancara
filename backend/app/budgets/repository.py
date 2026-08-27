"""Data-access layer for Budget, plus the spend-tracking query against Transaction."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.budgets.models import Budget
from app.merchants.models import Merchant
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
        """Card payments to merchants in this category, same category
        dimension AnalyticsRepository.spending_by_merchant_category groups
        by for the Analytics donut — a budget tracks real purchases at
        merchants of one category, so transfers and loan payments (neither
        is a "purchase" against any category) are excluded outright rather
        than through CASHBACK-style filtering."""
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
            total = Decimal("0")
            for transaction in rows:
                if not (period_start <= transaction.created_at <= period_end):
                    continue
                merchant = merchants_by_id.get(transaction.merchant_id) if transaction.merchant_id else None
                if merchant is not None and merchant.category == category:
                    total += transaction.amount
            return total

        stmt = (
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .select_from(Transaction)
            .join(Merchant, Merchant.id == Transaction.merchant_id)
            .where(
                Transaction.initiator_user_id == user_id,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.type == TransactionType.CARD_PAYMENT,
                Transaction.currency == currency,
                Merchant.category == category,
                Transaction.created_at >= period_start,
                Transaction.created_at <= period_end,
            )
        )
        return self.db.scalar(stmt) or Decimal("0")
