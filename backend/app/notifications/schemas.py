"""Pydantic schemas for the notifications module."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.notifications.models import NotificationType


class NotificationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    message: str
    related_transaction_id: uuid.UUID | None
    is_read: bool
    created_at: datetime


class UnreadCount(BaseModel):
    unread_count: int
