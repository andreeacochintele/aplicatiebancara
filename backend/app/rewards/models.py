"""RewardAccount and RewardTransaction — bank reward points ledger (architecture.md §11).

Points track spend-driven rewards independent of wallet money — the same
simplification `savings_goals.current_amount` already uses (see
app/savings/models.py): nothing here moves real wallet balance, which stays
owned by the transaction engine in app/transactions/service.py.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class RewardTransactionType(str, enum.Enum):
    EARN = "EARN"
    SPEND = "SPEND"
    ADJUSTMENT = "ADJUSTMENT"


class RewardAccount(Base):
    __tablename__ = "reward_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    points_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RewardTransaction(Base):
    __tablename__ = "reward_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reward_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reward_accounts.id"), nullable=False
    )
    source_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )
    type: Mapped[RewardTransactionType] = mapped_column(
        Enum(RewardTransactionType, name="reward_transaction_type"), nullable=False
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
