"""Business logic for a user's company profiles. A user can represent more
than one company; exactly one is `is_active` at a time (same one-flag-per-
user invariant as Wallet.is_main / WalletService.set_main_wallet)."""
import uuid

from sqlalchemy.orm import Session

from app.business.models import BusinessProfile
from app.business.repository import BusinessProfileRepository
from app.business.schemas import BusinessProfileCreate, BusinessProfileUpdate
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
