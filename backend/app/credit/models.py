"""Credit score domain models.

Credit scoring is deterministic mock logic for the demo app. No external
credit bureau data is integrated here.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class CreditApplicationType(str, enum.Enum):
    PERSONAL_LOAN = "PERSONAL_LOAN"
    CREDIT_CARD = "CREDIT_CARD"


class CreditApplicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CreditProfile(Base):
    __tablename__ = "credit_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    current_score: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    existing_debt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner = relationship("User")
    score_history = relationship("CreditScoreHistory", back_populates="profile", cascade="all, delete-orphan")


class CreditScoreHistory(Base):
    __tablename__ = "credit_score_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_profiles.id"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile = relationship("CreditProfile", back_populates="score_history")


class CreditApplication(Base):
    __tablename__ = "credit_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type: Mapped[CreditApplicationType] = mapped_column(
        Enum(CreditApplicationType, name="credit_application_type"), nullable=False
    )
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    requested_term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offered_interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    offered_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    credit_score_at_application: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CreditApplicationStatus] = mapped_column(
        Enum(CreditApplicationStatus, name="credit_application_status"),
        default=CreditApplicationStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner = relationship("User")
