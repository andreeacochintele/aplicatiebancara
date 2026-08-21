"""Pydantic schemas for the users module."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.enums import UserRole, UserStatus, UserType
from app.core.validation import (
    Cnp,
    DateOfBirth,
    MonthlyIncome,
    Occupation,
    OptionalAddressToken,
    OptionalFreeText100,
    OptionalFreeText255,
    PersonName,
    PhoneNumber,
    PostalCode,
    StreetName,
    StrongPassword,
    cnp_birth_date,
)
from app.users.models import EmploymentStatus, KycDocumentStatus


class UserCreate(BaseModel):
    email: EmailStr
    phone: PhoneNumber | None = None
    password: StrongPassword
    first_name: PersonName
    last_name: PersonName
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
    cnp: Cnp
    date_of_birth: DateOfBirth
    citizenship: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    county: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    street: StreetName
    street_number: str = Field(min_length=1, max_length=32)
    building: OptionalAddressToken = None
    staircase: OptionalAddressToken = None
    apartment: OptionalAddressToken = None
    postal_code: PostalCode = None

    @model_validator(mode="after")
    def _cnp_matches_birth_date(self) -> "OnboardingStep2Update":
        expected = cnp_birth_date(self.cnp)
        if expected is not None and expected != self.date_of_birth:
            raise ValueError("CNP does not match the date of birth provided")
        return self


class OnboardingStep4Update(BaseModel):
    occupation: Occupation = None
    employer: OptionalFreeText255 = None
    industry: OptionalFreeText100 = None
    employment_status: EmploymentStatus | None = None
    income_source: OptionalFreeText100 = None
    approximate_monthly_income: MonthlyIncome = None
    account_purpose: str | None = Field(default=None, max_length=1000)


class ProfileUpdate(BaseModel):
    first_name: PersonName | None = None
    last_name: PersonName | None = None
    phone: PhoneNumber | None = None
    step_2: OnboardingStep2Update | None = None
    employment: OnboardingStep4Update | None = None
