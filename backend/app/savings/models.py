"""SavingsGoal — a target amount a user is saving toward, optionally by a date
(architecture.md §14).

current_amount is backed by real money: SavingsService.contribute() debits a
real wallet through the standard Transaction + WalletLedgerEntry ledger
(TransactionType.SAVINGS_CONTRIBUTION) before ever incrementing it, and
withdraw() does the reverse (SAVINGS_WITHDRAWAL, a CREDIT back to a wallet).
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class SavingsGoalStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[SavingsGoalStatus] = mapped_column(
        Enum(SavingsGoalStatus, name="savings_goal_status"), default=SavingsGoalStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
