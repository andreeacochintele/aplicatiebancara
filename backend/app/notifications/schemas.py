"""Pydantic schemas for the notifications module."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationPublic(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    message: str
    related_transaction_id: uuid.UUID | None
    is_read: bool
    created_at: datetime
