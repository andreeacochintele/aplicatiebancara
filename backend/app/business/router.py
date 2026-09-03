"""Business module: a user's company profiles (architecture.md's Business
Profiles table). A user can represent more than one company; `/profile`
(singular) returns whichever one is currently active, `/profiles` manages
the full list. Transaction export lives in app/exports, not here.

KYB verification (business_profiles.verification_status + the documents a
business uploads to prove its identity) is admin-reviewed, same "engine
flags, admin decides" separation as fraud/credit — this router never
verifies or rejects a profile on its own."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.auth.dependencies import require_admin, require_business
from app.business import anaf_client
from app.business.schemas import (
    BusinessDocumentCreate,
    BusinessDocumentPublic,
    BusinessDocumentContentPublic,
    BusinessDocumentReview,
    BusinessProfileCreate,
    BusinessProfileDecision,
    BusinessProfilePublic,
    BusinessProfileUpdate,
    CuiLookupResult,
)
from app.business.service import BusinessDocumentService, BusinessProfileService
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/business", tags=["business"])


@router.get("/lookup-cui/{cui}", response_model=CuiLookupResult)
def lookup_cui(
    cui: str,
    current_user: User = Depends(require_business),
):
    return anaf_client.lookup_cui(cui)


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
    profile = BusinessProfileService(db).create_profile(current_user.id, payload)
    db.commit()
    return profile


@router.put("/profiles/{profile_id}", response_model=BusinessProfilePublic)
def update_business_profile(
    profile_id: uuid.UUID,
    payload: BusinessProfileUpdate,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    profile = BusinessProfileService(db).update_profile(current_user.id, profile_id, payload)
    db.commit()
    return profile


@router.put("/profiles/{profile_id}/activate", response_model=BusinessProfilePublic)
def activate_business_profile(
    profile_id: uuid.UUID,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    profile = BusinessProfileService(db).set_active_profile(current_user.id, profile_id)
    db.commit()
    return profile


@router.get("/profiles/{profile_id}/documents", response_model=list[BusinessDocumentPublic])
def list_business_profile_documents(
    profile_id: uuid.UUID,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    return BusinessDocumentService(db).list_for_profile(current_user.id, profile_id)


@router.post(
    "/profiles/{profile_id}/documents", response_model=BusinessDocumentPublic, status_code=status.HTTP_201_CREATED
)
def upload_business_profile_document(
    profile_id: uuid.UUID,
    payload: BusinessDocumentCreate,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
):
    document = BusinessDocumentService(db).upload_document(current_user.id, profile_id, payload)
    db.commit()
    return document


@router.get("/admin/profiles", response_model=list[BusinessProfilePublic])
def list_all_business_profiles(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return BusinessProfileService(db).list_all_for_admin()


@router.get("/admin/documents", response_model=list[BusinessDocumentPublic])
def list_all_business_documents(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return BusinessDocumentService(db).list_all_for_admin()


@router.get("/admin/documents/{document_id}/content", response_model=BusinessDocumentContentPublic)
def get_business_document_content(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    document = BusinessDocumentService(db).get_document_content_for_admin(document_id)
    AuditService(db).log_action(
        admin.id,
        action="VIEW_CONTENT",
        entity_type="BUSINESS_DOCUMENT",
        entity_id=document_id,
    )
    db.commit()
    return document


@router.patch("/admin/documents/{document_id}/review", response_model=BusinessDocumentPublic)
def review_business_document(
    document_id: uuid.UUID,
    payload: BusinessDocumentReview,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service = BusinessDocumentService(db)
    document = service.review_document(document_id, admin.id, payload)
    AuditService(db).log_action(
        admin.id,
        action=payload.status.value,
        entity_type="BUSINESS_DOCUMENT",
        entity_id=document.id,
        new_data={"status": document.status.value},
    )
    db.commit()
    return document


@router.patch("/admin/profiles/{profile_id}/decision", response_model=BusinessProfilePublic)
def decide_business_profile(
    profile_id: uuid.UUID,
    payload: BusinessProfileDecision,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service = BusinessProfileService(db)
    profile = service.decide_profile(profile_id, admin.id, payload)
    AuditService(db).log_action(
        admin.id,
        action=payload.status.value,
        entity_type="BUSINESS_PROFILE",
        entity_id=profile.id,
        new_data={"status": profile.verification_status.value},
    )
    db.commit()
    return profile
