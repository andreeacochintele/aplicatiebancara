"""Notification center endpoints, scoped to the authenticated user (architecture.md §26)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.notifications.schemas import NotificationPublic
from app.notifications.service import NotificationsService
from app.users.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationPublic])
def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationPublic]:
    return NotificationsService(db).list_for_user(current_user.id, unread_only)


@router.post("/{notification_id}/read", response_model=NotificationPublic)
def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPublic:
    result = NotificationsService(db).mark_read(current_user.id, notification_id)
    db.commit()
    return result
