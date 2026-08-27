"""Pydantic schemas for authentication endpoints."""
from pydantic import BaseModel, EmailStr, Field

from app.core.validation import PersonName, PhoneNumber, StrongPassword
from app.users.schemas import UserPublic


class RegisterRequest(BaseModel):
    email: EmailStr
    phone: PhoneNumber | None = None
    password: StrongPassword
    first_name: PersonName
    last_name: PersonName
    referral_code: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    user: UserPublic
    tokens: TokenResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RevokedSessionsResponse(BaseModel):
    revoked_sessions: int
