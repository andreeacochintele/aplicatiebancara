"""Pydantic schemas for the audit module."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminAuditLogPublic(BaseModel):
    id: uuid.UUID
    admin_user_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    old_data: dict[str, Any] | None
    new_data: dict[str, Any] | None
    created_at: datetime
