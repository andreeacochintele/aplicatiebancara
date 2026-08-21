"""Notification center (architecture.md §26).

`create` is called from other modules when something notification-worthy
happens — e.g. app/merchants/service.py after crediting cashback — the same
cross-module pattern already used for reading cards/transactions elsewhere
in this codebase, just for writing here instead.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.notifications.models import Notification
from app.notifications.repository import NotificationRepository
from app.notifications.schemas import NotificationPublic


class NotificationsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = NotificationRepository(db)

    def create(
        self,
        user_id: uuid.UUID,
        type: str,
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

    def list_for_user(self, user_id: uuid.UUID, unread_only: bool = False) -> list[NotificationPublic]:
        return [self._to_public(n) for n in self.repository.list_for_user(user_id, unread_only)]

    def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> NotificationPublic:
        notification = self.repository.get_by_id(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification not found")
        notification.is_read = True
        self.db.flush()
        return self._to_public(notification)

    @staticmethod
    def _to_public(notification: Notification) -> NotificationPublic:
        return NotificationPublic(
            id=notification.id,
            type=notification.type,
            title=notification.title,
            message=notification.message,
            related_transaction_id=notification.related_transaction_id,
            is_read=notification.is_read,
            created_at=notification.created_at,
        )
