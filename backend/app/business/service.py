"""Business logic for a user's company profiles. A user can represent more
than one company; exactly one is `is_active` at a time (same one-flag-per-
user invariant as Wallet.is_main / WalletService.set_main_wallet)."""
import base64
import binascii
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.business.models import BusinessDocument, BusinessProfile, BusinessVerificationStatus
from app.business.repository import BusinessDocumentRepository, BusinessProfileRepository
from app.business.schemas import (
    BusinessDocumentCreate,
    BusinessDocumentReview,
    BusinessProfileCreate,
    BusinessProfileDecision,
    BusinessProfileUpdate,
)
from app.core.exceptions import NotFoundError, ValidationError


class BusinessProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = BusinessProfileRepository(db)

    def list_profiles(self, user_id: uuid.UUID) -> list[BusinessProfile]:
        return self.repository.list_for_user(user_id)

    def get_active_profile(self, user_id: uuid.UUID) -> BusinessProfile | None:
        return next((p for p in self.repository.list_for_user(user_id) if p.is_active), None)

    def create_profile(self, user_id: uuid.UUID, data: BusinessProfileCreate) -> BusinessProfile:
        existing = self.repository.list_for_user(user_id)
        profile = BusinessProfile(
            user_id=user_id,
            is_active=not existing,  # first company for this user is active by default
            **data.model_dump(),
        )
        return self.repository.add(profile)

    def update_profile(self, user_id: uuid.UUID, profile_id: uuid.UUID, data: BusinessProfileUpdate) -> BusinessProfile:
        profile = self._get_owned(user_id, profile_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        self.db.flush()
        return profile

    def set_active_profile(self, user_id: uuid.UUID, profile_id: uuid.UUID) -> BusinessProfile:
        profiles = self.repository.list_for_user(user_id)
        target = next((p for p in profiles if p.id == profile_id), None)
        if target is None:
            raise NotFoundError("Business profile not found")
        for profile in profiles:
            profile.is_active = profile.id == profile_id
        self.db.flush()
        return target

    def _get_owned(self, user_id: uuid.UUID, profile_id: uuid.UUID) -> BusinessProfile:
        profile = self.repository.get_by_id(profile_id)
        if profile is None or profile.user_id != user_id:
            raise NotFoundError("Business profile not found")
        return profile

    def list_all_for_admin(self) -> list[BusinessProfile]:
        return self.repository.list_all()

    def decide_profile(
        self, profile_id: uuid.UUID, admin_id: uuid.UUID, decision: BusinessProfileDecision
    ) -> BusinessProfile:
        profile = self.repository.get_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Business profile not found")
        if decision.status == BusinessVerificationStatus.PENDING_VERIFICATION:
            raise ValidationError("A KYB decision must verify or reject the profile, not reset it to pending")
        if decision.status == BusinessVerificationStatus.REJECTED and not (decision.rejection_reason or "").strip():
            raise ValidationError("A rejection reason is required")

        profile.verification_status = decision.status
        profile.verified_at = datetime.now(timezone.utc)
        profile.verified_by_admin_id = admin_id
        profile.rejection_reason = (
            decision.rejection_reason if decision.status == BusinessVerificationStatus.REJECTED else None
        )
        self.db.flush()
        return profile


class BusinessDocumentService:
    """Proof-of-company uploads a business account attaches to its profile
    for KYB review — registration certificate, articles of association,
    legal representative ID, optional proof of address. Mirrors
    credit/service.py's document-upload validation (base64 content matching
    the declared file_size) rather than inventing a second convention."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = BusinessDocumentRepository(db)
        self.profiles = BusinessProfileRepository(db)

    def list_for_profile(self, user_id: uuid.UUID, profile_id: uuid.UUID) -> list[BusinessDocument]:
        self._get_owned_profile(user_id, profile_id)
        return self.repository.list_for_profile(profile_id)

    def list_all_for_admin(self) -> list[BusinessDocument]:
        return self.repository.list_all()

    def upload_document(
        self, user_id: uuid.UUID, profile_id: uuid.UUID, data: BusinessDocumentCreate
    ) -> BusinessDocument:
        self._get_owned_profile(user_id, profile_id)
        if data.file_size < 0:
            raise ValidationError("Document file size cannot be negative")
        if not data.file_name.strip():
            raise ValidationError("Document file name is required")
        content_base64 = data.content_base64.strip() if data.content_base64 else None
        if content_base64 is not None:
            try:
                decoded_size = len(base64.b64decode(content_base64, validate=True))
            except (binascii.Error, ValueError) as exc:
                raise ValidationError("Document content must be valid base64") from exc
            if decoded_size != data.file_size:
                raise ValidationError("Document file size does not match uploaded content")

        document = BusinessDocument(
            business_profile_id=profile_id,
            user_id=user_id,
            document_type=data.document_type,
            file_name=data.file_name,
            content_type=data.content_type,
            file_size=data.file_size,
            content_base64=content_base64,
        )
        return self.repository.add(document)

    def get_document_content_for_admin(self, document_id: uuid.UUID) -> BusinessDocument:
        document = self.repository.get_by_id(document_id)
        if document is None:
            raise NotFoundError("Business document not found")
        return document

    def review_document(
        self, document_id: uuid.UUID, admin_id: uuid.UUID, data: BusinessDocumentReview
    ) -> BusinessDocument:
        document = self.repository.get_by_id(document_id)
        if document is None:
            raise NotFoundError("Business document not found")
        document.status = data.status
        document.review_note = data.review_note
        document.reviewed_at = datetime.now(timezone.utc)
        document.reviewed_by_admin_id = admin_id
        self.db.flush()
        return document

    def _get_owned_profile(self, user_id: uuid.UUID, profile_id: uuid.UUID) -> BusinessProfile:
        profile = self.profiles.get_by_id(profile_id)
        if profile is None or profile.user_id != user_id:
            raise NotFoundError("Business profile not found")
        return profile
