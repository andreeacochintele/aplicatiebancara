"""Data-access layer for analytics — read-only aggregate queries over Transaction."""
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.transactions.models import Transaction, TransactionStatus


class AnalyticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def spending_by_type(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[tuple]:
        stmt = (
            select(
                Transaction.type,
                Transaction.currency,
                func.sum(Transaction.amount),
                func.count(Transaction.id),
            )
            .where(
                Transaction.initiator_user_id == user_id,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.created_at >= period_start,
                Transaction.created_at < period_end,
            )
            .group_by(Transaction.type, Transaction.currency)
        )
        return list(self.db.execute(stmt).all())

    def completed_transactions_in_range(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> list[tuple]:
        stmt = select(Transaction.amount, Transaction.currency, Transaction.created_at).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= period_start,
            Transaction.created_at <= period_end,
        )
        return list(self.db.execute(stmt).all())
