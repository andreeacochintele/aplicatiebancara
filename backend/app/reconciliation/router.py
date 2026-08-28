"""Admin wallet-ledger reconciliation endpoint. Read-only — reports
discrepancies, never corrects them (a stored balance vs. its ledger
disagreeing is exactly the kind of thing an admin should look at by hand,
not have silently auto-fixed)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.reconciliation.schemas import ReconciliationReport
from app.reconciliation.service import ReconciliationService
from app.users.models import User

router = APIRouter(prefix="/admin/reconciliation", tags=["reconciliation"])


@router.get("", response_model=ReconciliationReport)
def run_reconciliation(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReconciliationReport:
    return ReconciliationService(db).check_all_wallets()
