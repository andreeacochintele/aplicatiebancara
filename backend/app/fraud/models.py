"""FraudCase and FraudFlag — deterministic fraud engine output (architecture.md §32).

A FraudCase is created only when a transaction's computed risk score crosses
the threshold (see fraud/service.py); the transaction's funds are held via
WalletLedgerEntry(HOLD) at the same time. Admin approve/reject decisions are
tracked directly on this table (decided_by_admin_id/decided_at/status) —
there's no separate admin_audit_logs table yet, so this is the audit trail
for fraud decisions specifically.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class FraudCaseStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FraudFlagCode(str, enum.Enum):
    NEW_DEVICE = "NEW_DEVICE"
    HIGH_AMOUNT = "HIGH_AMOUNT"
    UNUSUAL_COUNTRY = "UNUSUAL_COUNTRY"
    REWARD_ABUSE_PATTERN = "REWARD_ABUSE_PATTERN"
    HIGH_VELOCITY = "HIGH_VELOCITY"


class FraudCase(Base):
    __tablename__ = "fraud_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[FraudCaseStatus] = mapped_column(
        Enum(FraudCaseStatus, name="fraud_case_status"), default=FraudCaseStatus.PENDING_REVIEW, nullable=False
    )
    hold_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    decided_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Cache for the (not yet implemented) Fraud Investigation Agent's output —
    # see feature/dev4/ai-agents. Unused until that lands.
    agent_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)

    flags = relationship("FraudFlag", back_populates="case")


class FraudFlag(Base):
    __tablename__ = "fraud_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fraud_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fraud_cases.id"), nullable=False)
    code: Mapped[FraudFlagCode] = mapped_column(Enum(FraudFlagCode, name="fraud_flag_code"), nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    case = relationship("FraudCase", back_populates="flags")
