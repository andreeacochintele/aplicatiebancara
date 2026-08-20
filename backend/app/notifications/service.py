"""Notification Center — architecture.md §26.

`notify()` is the extension point other domains call to raise a notification
(e.g. a completed transfer, a fraud hold, an earned cashback). It only ever
writes a row here; it never reaches into another domain's tables.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.notifications.models import Notification, NotificationType
from app.notifications.repository import NotificationRepository


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = NotificationRepository(db)

    def list_for_user(self, user_id: uuid.UUID) -> list[Notification]:
        return self.repository.list_for_user(user_id)

    def unread_count(self, user_id: uuid.UUID) -> int:
        return sum(1 for notification in self.repository.list_for_user(user_id) if not notification.is_read)

    def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        notification = self.repository.get_by_id(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification not found")
        notification.is_read = True
        self.db.flush()
        return notification

    def mark_all_read(self, user_id: uuid.UUID) -> int:
        unread = [n for n in self.repository.list_for_user(user_id) if not n.is_read]
        for notification in unread:
            notification.is_read = True
        self.db.flush()
        return len(unread)

    def notify(
        self,
        user_id: uuid.UUID,
        type: NotificationType,
        title: str,
        message: str,
        related_transaction_id: uuid.UUID | None = None,
    ) -> Notification:
        return self.repository.add(
            Notification(
                user_id=user_id,
                type=type,
                title=title,
                message=message,
                related_transaction_id=related_transaction_id,
            )
        )
