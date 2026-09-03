"""BusinessProfile - company details for BUSINESS user_type accounts
(architecture.md's "Business Profiles" table). A user can represent more
than one company (accountants/agencies often do), so this is one-to-many
with User rather than 1:1 like UserProfile — `is_active` marks which one is
currently selected, same pattern as Wallet.is_main.

Every new profile starts PENDING_VERIFICATION - a real bank cannot take a
company's own word for its identity (KYB: Know Your Business), so an admin
must review it, same "engine flags, admin decides" separation as the fraud
workflow. BusinessDocument mirrors credit/models.py's CreditDocument
(base64 content column, its own review status) rather than inventing a new
document-storage shape."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class BusinessVerificationStatus(str, enum.Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class BusinessDocumentType(str, enum.Enum):
    REGISTRATION_CERTIFICATE = "REGISTRATION_CERTIFICATE"
    ARTICLES_OF_ASSOCIATION = "ARTICLES_OF_ASSOCIATION"
    LEGAL_REPRESENTATIVE_ID = "LEGAL_REPRESENTATIVE_ID"
    PROOF_OF_ADDRESS = "PROOF_OF_ADDRESS"


class BusinessDocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    representative_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    business_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[BusinessVerificationStatus] = mapped_column(
        Enum(BusinessVerificationStatus, name="business_verification_status"),
        default=BusinessVerificationStatus.PENDING_VERIFICATION,
        nullable=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BusinessDocument(Base):
    __tablename__ = "business_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_profiles.id"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    document_type: Mapped[BusinessDocumentType] = mapped_column(
        Enum(BusinessDocumentType, name="business_document_type"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BusinessDocumentStatus] = mapped_column(
        Enum(BusinessDocumentStatus, name="business_document_status"),
        default=BusinessDocumentStatus.UPLOADED,
        nullable=False,
    )
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
