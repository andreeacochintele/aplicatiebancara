"""Pydantic schemas for the business module."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.business.models import BusinessDocumentStatus, BusinessDocumentType, BusinessVerificationStatus


class BusinessProfileCreate(BaseModel):
    company_name: str
    representative_name: str | None = None
    tax_id: str | None = None
    registration_number: str | None = None
    business_category: str | None = None


class BusinessProfileUpdate(BaseModel):
    company_name: str | None = None
    representative_name: str | None = None
    tax_id: str | None = None
    registration_number: str | None = None
    business_category: str | None = None


class CuiLookupResult(BaseModel):
    cui: str
    company_name: str
    registration_number: str | None
    address: str | None
    is_active: bool


class BusinessProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    company_name: str
    representative_name: str | None
    tax_id: str | None
    registration_number: str | None
    business_category: str | None
    is_active: bool
    verification_status: BusinessVerificationStatus
    verified_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class BusinessDocumentCreate(BaseModel):
    document_type: BusinessDocumentType
    file_name: str
    content_type: str | None = None
    file_size: int
    content_base64: str | None = None


class BusinessDocumentReview(BaseModel):
    status: BusinessDocumentStatus
    review_note: str | None = None


class BusinessDocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_profile_id: uuid.UUID
    user_id: uuid.UUID
    document_type: BusinessDocumentType
    file_name: str
    content_type: str | None
    file_size: int
    status: BusinessDocumentStatus
    review_note: str | None
    uploaded_at: datetime
    reviewed_at: datetime | None
    reviewed_by_admin_id: uuid.UUID | None


class BusinessDocumentContentPublic(BaseModel):
    id: uuid.UUID
    file_name: str
    content_type: str | None
    content_base64: str


class BusinessProfileDecision(BaseModel):
    status: BusinessVerificationStatus
    rejection_reason: str | None = None
