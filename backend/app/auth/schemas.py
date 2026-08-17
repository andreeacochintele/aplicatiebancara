"""Pydantic schemas for authentication endpoints."""
from pydantic import BaseModel, EmailStr

from app.users.schemas import UserPublic


class RegisterRequest(BaseModel):
    email: EmailStr
    phone: str | None = None
    password: str
    first_name: str
    last_name: str


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
