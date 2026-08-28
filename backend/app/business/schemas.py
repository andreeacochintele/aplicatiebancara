"""Pydantic schemas for the business module."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    created_at: datetime
    updated_at: datetime
