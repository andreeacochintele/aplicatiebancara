"""Data-access layer for AdminAuditLog."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AdminAuditLog
from app.supabase import is_supabase_session


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, log: AdminAuditLog) -> AdminAuditLog:
        if is_supabase_session(self.db):
            return self.db.add(log)
        self.db.add(log)
        self.db.flush()
        return log

    def list_all(self, entity_type: str | None = None, limit: int = 100, offset: int = 0) -> list[AdminAuditLog]:
        if is_supabase_session(self.db):
            params = {"order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
            if entity_type is not None:
                params["entity_type"] = f"eq.{entity_type}"
            return self.db.fetch_many(AdminAuditLog, params)
        stmt = select(AdminAuditLog)
        if entity_type is not None:
            stmt = stmt.where(AdminAuditLog.entity_type == entity_type)
        stmt = stmt.order_by(AdminAuditLog.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt))
