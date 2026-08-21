"""Data-access layer for Notification."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.notifications.models import Notification
from app.supabase import is_supabase_session


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, notification: Notification) -> Notification:
        if is_supabase_session(self.db):
            return self.db.add(notification)
        self.db.add(notification)
        self.db.flush()
        return notification

    def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        if is_supabase_session(self.db):
            return self.db.get(Notification, notification_id)
        return self.db.get(Notification, notification_id)

    def list_for_user(self, user_id: uuid.UUID, unread_only: bool = False) -> list[Notification]:
        if is_supabase_session(self.db):
            params = {"user_id": f"eq.{user_id}", "order": "created_at.desc"}
            if unread_only:
                params["is_read"] = "eq.false"
            return self.db.fetch_many(Notification, params)
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.order_by(Notification.created_at.desc())
        return list(self.db.scalars(stmt))
