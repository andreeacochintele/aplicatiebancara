"""Business logic for user creation. Enforces uniqueness of email/phone."""
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.core.security import hash_password
from app.notifications.service import NotificationsService
from app.rewards.service import REFERRAL_BONUS_POINTS, RewardsService
from app.users.models import KycDocumentStatus, User, UserAddress, UserEmploymentProfile, UserOnboardingState, UserProfile
from app.users.repository import UserRepository
from app.users.schemas import OnboardingStep2Update, OnboardingStep4Update, ProfileUpdate, UserCreate, UserFullProfilePublic


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
        self.repository.add(user)
        self.ensure_profile_records(user, legacy_completed=False)

        # Best-effort: a notification failure must never make registration
        # itself look like it failed.
        try:
            self.notifications.create(
                user.id,
                type="SYSTEM",
                title="Welcome to Aurora",
                message=f"Hi {user.first_name}, your account is ready. Set up your first wallet to get started.",
            )
        except Exception:
            pass

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
                pass

        return user

    def get_full_profile(self, user: User) -> UserFullProfilePublic:
        state, profile, address, employment = self.ensure_profile_records(user)
        return UserFullProfilePublic(
            user=user,
            onboarding=state,
            profile=profile,
            address=address,
            employment=employment,
        )

    def update_onboarding_step_2(self, user: User, data: OnboardingStep2Update) -> UserFullProfilePublic:
        state, profile, address, _employment = self.ensure_profile_records(user)
        if state.pending_step != 2:
            raise ValidationError("Onboarding step 2 is not the current pending step")
        self._apply_step_2(user.id, profile, address, data)
        state.pending_step = 3
        state.completed = False
        self.repository.flush()
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
        if data.step_2 is not None:
            _state, profile, address, _employment = self.ensure_profile_records(user)
            self._apply_step_2(user.id, profile, address, data.step_2)
        if data.employment is not None:
            _state, _profile, _address, employment = self.ensure_profile_records(user)
            self._apply_employment(employment, data.employment)
        self.repository.flush()
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
