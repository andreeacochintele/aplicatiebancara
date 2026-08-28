"""User - one of the four core domain entities."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole, UserStatus, UserType
from app.database import Base, utcnow


class KycDocumentStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    PLACEHOLDER = "PLACEHOLDER"  # legacy value from before real upload existed; no longer assigned
    VERIFIED = "VERIFIED"  # automated MRZ + cross-check passed
    NEEDS_REVIEW = "NEEDS_REVIEW"  # 3 failed attempts; awaiting admin decision
    APPROVED = "APPROVED"  # admin approved after manual review
    REJECTED = "REJECTED"  # admin rejected after manual review


class MrzFormatCode(str, enum.Enum):
    TD1 = "TD1"  # new card, ID-1 size (2021+)
    TD2 = "TD2"  # old card, ID-2 size (1997-2021)


class EmploymentStatus(str, enum.Enum):
    EMPLOYED = "EMPLOYED"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    STUDENT = "STUDENT"
    UNEMPLOYED = "UNEMPLOYED"
    RETIRED = "RETIRED"
    OTHER = "OTHER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.USER, nullable=False)
    user_type: Mapped[UserType] = mapped_column(
        Enum(UserType, name="user_type"), default=UserType.PERSONAL, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.ACTIVE, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    wallets = relationship("Wallet", back_populates="owner", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("UserDevice", back_populates="user", cascade="all, delete-orphan")
    onboarding_state = relationship(
        "UserOnboardingState", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    address = relationship("UserAddress", back_populates="user", uselist=False, cascade="all, delete-orphan")
    employment_profile = relationship(
        "UserEmploymentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserOnboardingState(Base):
    __tablename__ = "user_onboarding_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    pending_step: Mapped[int | None] = mapped_column(Integer, default=2, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    step_4_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    identity_document_status: Mapped[KycDocumentStatus] = mapped_column(
        Enum(KycDocumentStatus, name="kyc_document_status"),
        default=KycDocumentStatus.NOT_STARTED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="onboarding_state")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    cnp: Mapped[str | None] = mapped_column(String(13), unique=True, index=True, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    citizenship: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="profile")


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    county: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    building: Mapped[str | None] = mapped_column(String(32), nullable=True)
    staircase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    apartment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="address")


class UserEmploymentProfile(Base):
    __tablename__ = "user_employment_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    occupation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_status: Mapped[EmploymentStatus | None] = mapped_column(
        Enum(EmploymentStatus, name="employment_status"), nullable=True
    )
    income_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approximate_monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    account_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="employment_profile")


class IdentityDocument(Base):
    """Onboarding step 3: the user's ID card (front + back), the data
    deterministically extracted from its MRZ, and the outcome of matching
    that data against the profile from step 2. Same upload+review shape as
    `CreditDocument` (app/credit/models.py). One row per user - a retry
    overwrites the previous attempt's images/extraction rather than
    accumulating a history, per the confirmed 3-attempts-then-review flow."""

    __tablename__ = "identity_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)

    front_image_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    back_image_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_format: Mapped[MrzFormatCode | None] = mapped_column(Enum(MrzFormatCode, name="mrz_format_code"), nullable=True)

    extracted_surname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_given_names: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_cnp: Mapped[str | None] = mapped_column(String(13), nullable=True)
    extracted_date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    extracted_date_of_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)

    mrz_checks_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cross_check_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[KycDocumentStatus] = mapped_column(
        Enum(KycDocumentStatus, name="kyc_document_status"),
        default=KycDocumentStatus.NOT_STARTED,
        nullable=False,
    )
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by_admin_id])
