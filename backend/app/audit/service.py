"""Admin audit log (architecture.md §27).

log_action() is meant to be called from other modules' services, from
inside the same DB transaction as the admin action it records (e.g.
FraudService.approve/reject, CardService.freeze/unfreeze) — it does not
commit and does not swallow exceptions, so the audit row and the action it
describes succeed or fail together.
"""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.audit.models import AdminAuditLog
from app.audit.repository import AuditRepository
from app.audit.schemas import AdminAuditLogPublic


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AuditRepository(db)

    def log_action(
        self,
        admin_user_id: uuid.UUID,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        old_data: dict[str, Any] | None = None,
        new_data: dict[str, Any] | None = None,
    ) -> AdminAuditLog:
        return self.repository.add(
            AdminAuditLog(
                admin_user_id=admin_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_data=old_data,
                new_data=new_data,
            )
        )

    def list_all(self, entity_type: str | None = None, limit: int = 100, offset: int = 0) -> list[AdminAuditLogPublic]:
        return [self._to_public(log) for log in self.repository.list_all(entity_type, limit, offset)]

    @staticmethod
    def _to_public(log: AdminAuditLog) -> AdminAuditLogPublic:
        return AdminAuditLogPublic(
            id=log.id,
            admin_user_id=log.admin_user_id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            old_data=log.old_data,
            new_data=log.new_data,
            created_at=log.created_at,
        )
