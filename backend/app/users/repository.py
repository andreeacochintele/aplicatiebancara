"""Data-access layer for User. No business rules here, only queries."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.users.models import IdentityDocument, User, UserAddress, UserEmploymentProfile, UserOnboardingState, UserProfile


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        if is_supabase_session(self.db):
            return self.db.get(User, user_id)
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(User, {"email": f"eq.{email}"})
        return self.db.scalar(select(User).where(User.email == email))

    def get_by_phone(self, phone: str) -> User | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(User, {"phone": f"eq.{phone}"})
        return self.db.scalar(select(User).where(User.phone == phone))

    def list_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(User, {"limit": str(limit), "offset": str(offset)})
        return list(self.db.scalars(select(User).limit(limit).offset(offset)))

    def add(self, user: User) -> User:
        if is_supabase_session(self.db):
            return self.db.add(user)
        self.db.add(user)
        self.db.flush()
        return user

    def get_onboarding_state(self, user_id: uuid.UUID) -> UserOnboardingState | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(UserOnboardingState, {"user_id": f"eq.{user_id}"})
        return self.db.scalar(select(UserOnboardingState).where(UserOnboardingState.user_id == user_id))

    def get_profile(self, user_id: uuid.UUID) -> UserProfile | None:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_one(UserProfile, {"user_id": f"eq.{user_id}"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, UserProfile):
                    return None
                raise
        return self.db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))

    def get_profile_by_cnp(self, cnp: str) -> UserProfile | None:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_one(UserProfile, {"cnp": f"eq.{cnp}"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, UserProfile):
                    return None
                raise
        return self.db.scalar(select(UserProfile).where(UserProfile.cnp == cnp))

    def get_address(self, user_id: uuid.UUID) -> UserAddress | None:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_one(UserAddress, {"user_id": f"eq.{user_id}"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, UserAddress):
                    return None
                raise
        return self.db.scalar(select(UserAddress).where(UserAddress.user_id == user_id))

    def get_employment_profile(self, user_id: uuid.UUID) -> UserEmploymentProfile | None:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_one(UserEmploymentProfile, {"user_id": f"eq.{user_id}"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, UserEmploymentProfile):
                    return None
                raise
        return self.db.scalar(select(UserEmploymentProfile).where(UserEmploymentProfile.user_id == user_id))

    def get_identity_document(self, user_id: uuid.UUID) -> IdentityDocument | None:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_one(IdentityDocument, {"user_id": f"eq.{user_id}"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, IdentityDocument):
                    return None
                raise
        return self.db.scalar(select(IdentityDocument).where(IdentityDocument.user_id == user_id))

    def add_identity_document(self, document: IdentityDocument) -> IdentityDocument:
        return self._add_related(document)

    def add_onboarding_state(self, state: UserOnboardingState) -> UserOnboardingState:
        return self._add_related(state)

    def add_profile(self, profile: UserProfile) -> UserProfile:
        return self._add_related(profile)

    def add_address(self, address: UserAddress) -> UserAddress:
        return self._add_related(address)

    def add_employment_profile(self, employment: UserEmploymentProfile) -> UserEmploymentProfile:
        return self._add_related(employment)

    def flush(self) -> None:
        self.db.flush()

    def _add_related(self, model):
        if is_supabase_session(self.db):
            try:
                return self.db.add(model)
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, type(model)):
                    return model
                raise
        self.db.add(model)
        self.db.flush()
        return model

    def _is_missing_supabase_table(self, exc: RuntimeError, model: type[object]) -> bool:
        message = str(exc)
        return "PGRST205" in message and model.__tablename__ in message
