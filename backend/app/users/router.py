"""User-facing endpoints. Registration lives under /auth; this covers self-service profile reads."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.users.models import User
from app.users.schemas import (
    IdentityDocumentUpload,
    OnboardingStep2Update,
    OnboardingStep4Update,
    ProfileUpdate,
    UserFullProfilePublic,
    UserPublic,
)
from app.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def get_my_profile(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/me/profile", response_model=UserFullProfilePublic)
def get_my_full_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserFullProfilePublic:
    profile = UserService(db).get_full_profile(current_user)
    db.commit()
    return profile


@router.patch("/me/profile", response_model=UserFullProfilePublic)
def update_my_full_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserFullProfilePublic:
    profile = UserService(db).update_authenticated_profile(current_user, payload)
    db.commit()
    return profile


@router.patch("/me/onboarding/step-2", response_model=UserFullProfilePublic)
def update_onboarding_step_2(
    payload: OnboardingStep2Update,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserFullProfilePublic:
    profile = UserService(db).update_onboarding_step_2(current_user, payload)
    db.commit()
    return profile


@router.post("/me/onboarding/step-3/identity-document-placeholder", response_model=UserFullProfilePublic)
def create_identity_document_placeholder(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserFullProfilePublic:
    profile = UserService(db).create_identity_document_placeholder(current_user)
    db.commit()
    return profile


@router.post("/me/onboarding/step-3/identity-document", response_model=UserFullProfilePublic)
def submit_identity_document(
    payload: IdentityDocumentUpload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserFullProfilePublic:
    profile = UserService(db).submit_identity_document(current_user, payload)
    db.commit()
    return profile


@router.patch("/me/onboarding/step-4", response_model=UserFullProfilePublic)
def update_onboarding_step_4(
    payload: OnboardingStep4Update,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserFullProfilePublic:
    profile = UserService(db).update_onboarding_step_4(current_user, payload)
    db.commit()
    return profile


@router.post("/me/onboarding/step-4/skip", response_model=UserFullProfilePublic)
def skip_onboarding_step_4(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserFullProfilePublic:
    profile = UserService(db).skip_onboarding_step_4(current_user)
    db.commit()
    return profile
