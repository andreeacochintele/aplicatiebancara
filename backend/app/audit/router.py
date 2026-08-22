"""Admin audit log endpoint (architecture.md §27).

Read-only for now: writes happen via AuditService.log_action(), called from
other modules' services (fraud decisions, card freeze/unfreeze, ...) as they
adopt it — see app/audit/service.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit.schemas import AdminAuditLogPublic
from app.audit.service import AuditService
from app.auth.dependencies import require_admin
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AdminAuditLogPublic])
def list_audit_logs(
    entity_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminAuditLogPublic]:
    return AuditService(db).list_all(entity_type, limit, offset)
