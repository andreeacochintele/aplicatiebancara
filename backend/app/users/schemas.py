"""Pydantic schemas for the users module."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.enums import UserRole, UserStatus, UserType


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
