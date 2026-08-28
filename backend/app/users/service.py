"""Business logic for user creation. Enforces uniqueness of email/phone."""
import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError, is_unique_violation
from app.core.security import hash_password
from app.notifications.service import NotificationsService
from app.rewards.service import REFERRAL_BONUS_POINTS, RewardsService
from app.users.models import (
    IdentityDocument,
    KycDocumentStatus,
    User,
    UserAddress,
    UserEmploymentProfile,
    UserOnboardingState,
    UserProfile,
)
from app.users.mrz_extraction import ExtractedIdentity, decode_base64_image, extract_identity_from_back_image
from app.users.repository import UserRepository
from app.users.schemas import (
    IdentityDocumentUpload,
    OnboardingStep2Update,
    OnboardingStep4Update,
    ProfileUpdate,
    UserCreate,
    UserFullProfilePublic,
)

MAX_IDENTITY_DOCUMENT_ATTEMPTS = 3

# MRZ names are ICAO-transliterated (uppercase, diacritics stripped to their
# base Latin letter) - a plain case-sensitive comparison against the
# profile's own Romanian spelling would false-negative on every accented
# name, which is most of them.
_DIACRITIC_TRANSLATION = str.maketrans("ĂÂÎȘŞȚŢ", "AAISSTT")


def _normalize_name_for_comparison(value: str) -> str:
    return value.upper().translate(_DIACRITIC_TRANSLATION).strip()

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = UserRepository(db)
        self.notifications = NotificationsService(db)
        self.rewards = RewardsService(db)

    def create_user(self, data: UserCreate) -> User:
        if self.repository.get_by_email(data.email):
            raise ConflictError(f"Email '{data.email}' is already registered")
        if data.phone and self.repository.get_by_phone(data.phone):
            raise ConflictError(f"Phone '{data.phone}' is already registered")

        referrer_user_id = None
        referral_code = (data.referral_code or "").strip()
        if referral_code:
            referrer_user_id = self.rewards.get_referrer_user_id(referral_code)
            if referrer_user_id is None:
                raise ValidationError("Referral code not found")

        user = User(
            email=data.email,
            phone=data.phone,
            password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            user_type=data.user_type,
        )
        try:
            self.repository.add(user)
        except Exception as exc:
            if not is_unique_violation(exc):
                raise
            self.db.rollback()
            # The precondition checks above already ran, so this only fires
            # when a concurrent request won the race between check and
            # insert — same outer message either check would have raised.
            raise ConflictError("Email or phone is already registered") from None
        self.ensure_profile_records(user, legacy_completed=False)

        # Best-effort: a notification failure must never make registration
        # itself look like it failed.
        try:
            self.notifications.create(
                user.id,
                type="SYSTEM",
                title="Welcome to EasyB",
                message=f"Hi {user.first_name}, your account is ready. Set up your first wallet to get started.",
            )
        except Exception:
            logger.exception("Failed to create welcome notification for user %s", user.id)

        # Also best-effort: the referral code was already validated above, so
        # this should always succeed, but a hiccup crediting points must not
        # unwind an otherwise-successful registration.
        if referrer_user_id is not None:
            try:
                self.rewards.earn_points(
                    referrer_user_id,
                    REFERRAL_BONUS_POINTS,
                    description=f"Referral bonus: {user.first_name} {user.last_name} joined with your code",
                )
                self.notifications.create(
                    referrer_user_id,
                    type="REFERRAL",
                    title="Referral bonus!",
                    message=f"{user.first_name} {user.last_name} joined using your referral code. You earned {REFERRAL_BONUS_POINTS} points.",
                )
            except Exception:
                logger.exception("Failed to credit referral bonus for referrer %s", referrer_user_id)

        return user

    def get_full_profile(self, user: User) -> UserFullProfilePublic:
        state, profile, address, employment = self.ensure_profile_records(user)
        identity_document = self._ensure_identity_document(user.id)
        return UserFullProfilePublic(
            user=user,
            onboarding=state,
            profile=profile,
            address=address,
            employment=employment,
            identity_document=identity_document,
        )

    def update_onboarding_step_2(self, user: User, data: OnboardingStep2Update) -> UserFullProfilePublic:
        state, profile, address, _employment = self.ensure_profile_records(user)
        if state.pending_step != 2:
            raise ValidationError("Onboarding step 2 is not the current pending step")
        self._apply_step_2(user.id, profile, address, data)
        state.pending_step = 3
        state.completed = False
        try:
            self.repository.flush()
        except Exception as exc:
            if not is_unique_violation(exc):
                raise
            self.db.rollback()
            raise ConflictError("CNP is already registered") from None
        return self.get_full_profile(user)

    def create_identity_document_placeholder(self, user: User) -> UserFullProfilePublic:
        state, _profile, _address, _employment = self.ensure_profile_records(user)
        if state.pending_step != 3:
            raise ValidationError("Onboarding step 3 is not the current pending step")
        state.identity_document_status = KycDocumentStatus.PLACEHOLDER
        state.pending_step = 4
        state.completed = False
        self.repository.flush()
        return self.get_full_profile(user)

    def submit_identity_document(self, user: User, data: IdentityDocumentUpload) -> UserFullProfilePublic:
        """Used both during onboarding (step 3, pending_step == 3) and
        afterwards from the Profile page (state.completed - e.g. the user's
        ID card was renewed and they want to re-verify it)."""
        state, profile, _address, _employment = self.ensure_profile_records(user)
        if not (state.pending_step == 3 or state.completed):
            raise ValidationError("Onboarding step 3 is not the current pending step")

        document = self._ensure_identity_document(user.id)
        if document.status in (KycDocumentStatus.NEEDS_REVIEW, KycDocumentStatus.REJECTED):
            raise ValidationError("Your identity document is awaiting admin review and can't be resubmitted yet")

        extracted, extraction_failure_reason = self._extract_identity(data.back_image_base64)
        cross_check_passed = False
        failure_reason = extraction_failure_reason
        # An extraction-level problem (e.g. expired) takes priority over the
        # cross-check outcome - don't let a name/CNP/DOB match hide the fact
        # that the document itself is no good.
        if extracted is not None and extraction_failure_reason is None:
            cross_check_passed, failure_reason = self._cross_check_identity(user, profile, extracted)
        verified = extracted is not None and cross_check_passed

        is_voluntary_update = document.status == KycDocumentStatus.VERIFIED
        if is_voluntary_update and not verified:
            # Already verified (e.g. renewing an expiring ID) and this
            # attempt didn't pan out - report it without touching the
            # existing, still-genuinely-valid record. No attempt counting or
            # admin escalation here: unlike onboarding, nothing is blocked on
            # this succeeding, so the user can just try again anytime.
            raise ValidationError(failure_reason or "Could not verify the new identity document")

        document.front_image_base64 = data.front_image_base64
        document.back_image_base64 = data.back_image_base64
        document.attempt_count += 1
        document.mrz_checks_passed = extracted is not None
        document.cross_check_passed = cross_check_passed
        document.failure_reason = None if verified else failure_reason
        if extracted is not None:
            document.detected_format = extracted.detected_format
            document.extracted_surname = extracted.surname
            document.extracted_given_names = extracted.given_names
            document.extracted_cnp = extracted.cnp
            document.extracted_date_of_birth = extracted.date_of_birth
            document.extracted_date_of_expiry = extracted.date_of_expiry

        if verified:
            document.status = KycDocumentStatus.VERIFIED
            if state.pending_step == 3:
                state.pending_step = 4
                state.completed = False
        elif document.attempt_count >= MAX_IDENTITY_DOCUMENT_ATTEMPTS:
            # Hard block: the last attempt's images stay on the record for
            # an admin to review; the user can't keep retrying past this.
            document.status = KycDocumentStatus.NEEDS_REVIEW
        else:
            # Still under the attempt limit: stays retryable, failure_reason
            # explains what to fix.
            document.status = KycDocumentStatus.NOT_STARTED
        state.identity_document_status = document.status

        self.repository.flush()
        return self.get_full_profile(user)

    def update_onboarding_step_4(self, user: User, data: OnboardingStep4Update) -> UserFullProfilePublic:
        state, _profile, _address, employment = self.ensure_profile_records(user)
        if state.pending_step != 4:
            raise ValidationError("Onboarding step 4 is not the current pending step")
        self._apply_employment(employment, data)
        state.step_4_skipped = False
        state.pending_step = None
        state.completed = True
        self.repository.flush()
        return self.get_full_profile(user)

    def skip_onboarding_step_4(self, user: User) -> UserFullProfilePublic:
        state, _profile, _address, _employment = self.ensure_profile_records(user)
        if state.pending_step != 4:
            raise ValidationError("Onboarding step 4 is not the current pending step")
        state.step_4_skipped = True
        state.pending_step = None
        state.completed = True
        self.repository.flush()
        return self.get_full_profile(user)

    def update_authenticated_profile(self, user: User, data: ProfileUpdate) -> UserFullProfilePublic:
        if data.first_name is not None:
            user.first_name = data.first_name
        if data.last_name is not None:
            user.last_name = data.last_name
        if data.email is not None and data.email != user.email:
            existing = self.repository.get_by_email(data.email)
            if existing and existing.id != user.id:
                raise ConflictError(f"Email '{data.email}' is already registered")
            user.email = data.email
        if data.phone is not None and data.phone != user.phone:
            existing = self.repository.get_by_phone(data.phone)
            if existing and existing.id != user.id:
                raise ConflictError(f"Phone '{data.phone}' is already registered")
            user.phone = data.phone
        if data.step_2 is not None or data.employment is not None:
            state, profile, address, employment = self.ensure_profile_records(user)
            if state.pending_step is not None:
                raise ValidationError(
                    "Onboarding is not complete yet — finish the onboarding steps before editing your profile"
                )
            if data.step_2 is not None:
                self._apply_step_2(user.id, profile, address, data.step_2)
            if data.employment is not None:
                self._apply_employment(employment, data.employment)
        try:
            self.repository.flush()
        except Exception as exc:
            if not is_unique_violation(exc):
                raise
            self.db.rollback()
            raise ConflictError("Email, phone, or CNP is already registered") from None
        return self.get_full_profile(user)

    def ensure_profile_records(
        self, user: User, *, legacy_completed: bool = True
    ) -> tuple[UserOnboardingState, UserProfile, UserAddress, UserEmploymentProfile]:
        state = self.repository.get_onboarding_state(user.id)
        if state is None:
            state = self.repository.add_onboarding_state(
                UserOnboardingState(
                    user_id=user.id,
                    pending_step=None if legacy_completed else 2,
                    completed=legacy_completed,
                    step_4_skipped=False,
                )
            )
            if legacy_completed:
                state.pending_step = None
                state.completed = True

        profile = self.repository.get_profile(user.id)
        if profile is None:
            profile = self.repository.add_profile(UserProfile(user_id=user.id))

        address = self.repository.get_address(user.id)
        if address is None:
            address = self.repository.add_address(UserAddress(user_id=user.id))

        employment = self.repository.get_employment_profile(user.id)
        if employment is None:
            employment = self.repository.add_employment_profile(UserEmploymentProfile(user_id=user.id))

        return state, profile, address, employment

    def _ensure_identity_document(self, user_id: uuid.UUID) -> IdentityDocument:
        document = self.repository.get_identity_document(user_id)
        if document is None:
            document = self.repository.add_identity_document(IdentityDocument(user_id=user_id))
        return document

    def _extract_identity(self, back_image_base64: str) -> tuple[ExtractedIdentity | None, str | None]:
        image = decode_base64_image(back_image_base64)
        if image is None:
            return None, "Could not read the back-of-card photo — please retake it and try again"
        extracted = extract_identity_from_back_image(image)
        if extracted is None:
            return None, "Could not read the identity document's machine-readable zone — please retake the photo"
        if extracted.date_of_expiry is not None and extracted.date_of_expiry < date.today():
            return extracted, "This identity document has expired"
        return extracted, None

    def _cross_check_identity(
        self, user: User, profile: UserProfile, extracted: ExtractedIdentity
    ) -> tuple[bool, str | None]:
        expected_full_name = _normalize_name_for_comparison(f"{user.first_name} {user.last_name}")
        actual_full_name = _normalize_name_for_comparison(f"{extracted.given_names} {extracted.surname}")
        if expected_full_name != actual_full_name:
            return False, "The name on the document does not match your profile"
        if profile.date_of_birth is not None and extracted.date_of_birth != profile.date_of_birth:
            return False, "The date of birth on the document does not match your profile"
        if extracted.cnp is not None and profile.cnp is not None and extracted.cnp != profile.cnp:
            return False, "The CNP on the document does not match your profile"
        return True, None

    def _apply_step_2(
        self, user_id: uuid.UUID, profile: UserProfile, address: UserAddress, data: OnboardingStep2Update
    ) -> None:
        existing = self.repository.get_profile_by_cnp(data.cnp)
        if existing and existing.user_id != user_id:
            raise ConflictError("CNP is already registered")

        profile.cnp = data.cnp
        profile.date_of_birth = data.date_of_birth
        profile.citizenship = data.citizenship
        address.country = data.country
        address.county = data.county
        address.city = data.city
        address.street = data.street
        address.street_number = data.street_number
        address.building = data.building
        address.staircase = data.staircase
        address.apartment = data.apartment
        address.postal_code = data.postal_code

    def _apply_employment(self, employment: UserEmploymentProfile, data: OnboardingStep4Update) -> None:
        employment.occupation = data.occupation
        employment.employer = data.employer
        employment.industry = data.industry
        employment.employment_status = data.employment_status
        employment.income_source = data.income_source
        employment.approximate_monthly_income = (
            Decimal(data.approximate_monthly_income) if data.approximate_monthly_income is not None else None
        )
        employment.account_purpose = data.account_purpose
