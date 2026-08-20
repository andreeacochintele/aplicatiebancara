"""Notification Center endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.notifications.schemas import NotificationPublic, UnreadCount
from app.notifications.service import NotificationService
from app.users.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationPublic])
def list_my_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationPublic]:
    return NotificationService(db).list_for_user(current_user.id)


@router.get("/unread-count", response_model=UnreadCount)
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCount:
    return UnreadCount(unread_count=NotificationService(db).unread_count(current_user.id))


@router.patch("/read-all", response_model=UnreadCount)
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCount:
    NotificationService(db).mark_all_read(current_user.id)
    db.commit()
    return UnreadCount(unread_count=0)


@router.patch("/{notification_id}/read", response_model=NotificationPublic)
def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPublic:
    notification = NotificationService(db).mark_read(current_user.id, notification_id)
    db.commit()
    return notification
