"""Pydantic schemas for the users module."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserRole, UserStatus, UserType
from app.users.models import EmploymentStatus, KycDocumentStatus


class UserCreate(BaseModel):
    email: EmailStr
    phone: str | None = None
    password: str
    first_name: str
    last_name: str
    user_type: UserType = UserType.PERSONAL


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    phone: str | None
    first_name: str
    last_name: str
    role: UserRole
    user_type: UserType
    status: UserStatus
    created_at: datetime


class OnboardingStatePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pending_step: int | None
    completed: bool
    step_4_skipped: bool
    identity_document_status: KycDocumentStatus


class UserProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cnp: str | None
    date_of_birth: date | None
    citizenship: str | None


class UserAddressPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    country: str | None
    county: str | None
    city: str | None
    street: str | None
    street_number: str | None
    building: str | None
    staircase: str | None
    apartment: str | None
    postal_code: str | None


class UserEmploymentProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    occupation: str | None
    employer: str | None
    industry: str | None
    employment_status: EmploymentStatus | None
    income_source: str | None
    approximate_monthly_income: Decimal | None
    account_purpose: str | None


class UserFullProfilePublic(BaseModel):
    user: UserPublic
    onboarding: OnboardingStatePublic
    profile: UserProfilePublic
    address: UserAddressPublic
    employment: UserEmploymentProfilePublic


class OnboardingStep2Update(BaseModel):
    cnp: str = Field(min_length=13, max_length=13)
    date_of_birth: date
    citizenship: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    county: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    street: str = Field(min_length=1, max_length=255)
    street_number: str = Field(min_length=1, max_length=32)
    building: str | None = Field(default=None, max_length=32)
    staircase: str | None = Field(default=None, max_length=32)
    apartment: str | None = Field(default=None, max_length=32)
    postal_code: str | None = Field(default=None, max_length=32)


class OnboardingStep4Update(BaseModel):
    occupation: str | None = Field(default=None, max_length=100)
    employer: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    employment_status: EmploymentStatus | None = None
    income_source: str | None = Field(default=None, max_length=100)
    approximate_monthly_income: Decimal | None = Field(default=None, ge=0)
    account_purpose: str | None = Field(default=None, max_length=1000)


class ProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    step_2: OnboardingStep2Update | None = None
    employment: OnboardingStep4Update | None = None
