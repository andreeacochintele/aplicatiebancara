"""Credit score domain models.

Credit scoring is deterministic mock logic for the demo app. No external
credit bureau data is integrated here.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class CreditApplicationType(str, enum.Enum):
    PERSONAL_LOAN = "PERSONAL_LOAN"
    CREDIT_CARD = "CREDIT_CARD"


class LoanProductType(str, enum.Enum):
    PERSONAL_LOAN = "PERSONAL_LOAN"
    MORTGAGE = "MORTGAGE"
    AUTO_LOAN = "AUTO_LOAN"
    STUDENT_LOAN = "STUDENT_LOAN"
    HOME_IMPROVEMENT = "HOME_IMPROVEMENT"
    DEBT_CONSOLIDATION = "DEBT_CONSOLIDATION"


class CreditApplicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LoanStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAID = "PAID"
    CLOSED = "CLOSED"
    DEFAULTED = "DEFAULTED"


class LoanInstallmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    PARTIAL = "PARTIAL"
    OVERDUE = "OVERDUE"


class LoanPaymentType(str, enum.Enum):
    REGULAR = "REGULAR"
    EARLY_REPAYMENT = "EARLY_REPAYMENT"


class CreditProfile(Base):
    __tablename__ = "credit_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    current_score: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    existing_debt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)
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
    loan_product_type: Mapped[LoanProductType | None] = mapped_column(
        Enum(LoanProductType, name="loan_product_type"), nullable=True
    )
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)
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
    loan = relationship("Loan", back_populates="application", uselist=False)


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_applications.id"), unique=True, nullable=False
    )
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    outstanding_principal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus, name="loan_status"),
        default=LoanStatus.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner = relationship("User")
    application = relationship("CreditApplication", back_populates="loan")
    installments = relationship("LoanInstallment", back_populates="loan", cascade="all, delete-orphan")
    payments = relationship("LoanPayment", back_populates="loan", cascade="all, delete-orphan")


class LoanInstallment(Base):
    __tablename__ = "loan_installments"
    __table_args__ = (UniqueConstraint("loan_id", "installment_number", name="uq_loan_installments_loan_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False)
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fees_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    remaining_principal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[LoanInstallmentStatus] = mapped_column(
        Enum(LoanInstallmentStatus, name="loan_installment_status"),
        default=LoanInstallmentStatus.PENDING,
        nullable=False,
    )

    loan = relationship("Loan", back_populates="installments")


class LoanPayment(Base):
    __tablename__ = "loan_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    principal_paid: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    interest_paid: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fees_paid: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    payment_type: Mapped[LoanPaymentType] = mapped_column(
        Enum(LoanPaymentType, name="loan_payment_type"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    loan = relationship("Loan", back_populates="payments")
