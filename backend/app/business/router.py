"""Business module: a user's company profiles (architecture.md's Business
Profiles table). A user can represent more than one company; `/profile`
(singular) returns whichever one is currently active, `/profiles` manages
the full list. Transaction export lives in app/exports, not here."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_business
from app.business.schemas import BusinessProfileCreate, BusinessProfilePublic, BusinessProfileUpdate
from app.business.service import BusinessProfileService
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/business", tags=["business"])


@router.get("/profile", response_model=BusinessProfilePublic | None)
def get_active_business_profile(
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    return BusinessProfileService(db).get_active_profile(current_user.id)


@router.get("/profiles", response_model=list[BusinessProfilePublic])
def list_business_profiles(
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    return BusinessProfileService(db).list_profiles(current_user.id)


@router.post("/profiles", response_model=BusinessProfilePublic, status_code=status.HTTP_201_CREATED)
def create_business_profile(
    payload: BusinessProfileCreate,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    return BusinessProfileService(db).create_profile(current_user.id, payload)


@router.put("/profiles/{profile_id}", response_model=BusinessProfilePublic)
def update_business_profile(
    profile_id: uuid.UUID,
    payload: BusinessProfileUpdate,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    return BusinessProfileService(db).update_profile(current_user.id, profile_id, payload)


@router.put("/profiles/{profile_id}/activate", response_model=BusinessProfilePublic)
def activate_business_profile(
    profile_id: uuid.UUID,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    return BusinessProfileService(db).set_active_profile(current_user.id, profile_id)
