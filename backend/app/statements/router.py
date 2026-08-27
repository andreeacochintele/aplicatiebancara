"""Statement endpoints (architecture.md §24): a JSON preview and a CSV/PDF
export of a wallet's activity over a period. Computed on demand from the
existing ledger — there is no dedicated statements table. Every generated
export is logged to the shared `exports` table so it shows up in statement
history for any user, not just business accounts."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.exports.models import ExportFormat
from app.exports.schemas import ExportJobPublic
from app.statements.schemas import StatementPublic, StatementRequest
from app.statements.service import StatementService
from app.transactions.models import TransactionType
from app.users.models import User

router = APIRouter(prefix="/statements", tags=["statements"])


@router.get("", response_model=StatementPublic)
def get_statement(
    wallet_id: uuid.UUID = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    transaction_type: TransactionType | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StatementPublic:
    request = StatementRequest(
        wallet_id=wallet_id, date_from=date_from, date_to=date_to, transaction_type=transaction_type
    )
    return StatementService(db).generate(current_user.id, request)


@router.get("/export")
def export_statement(
    wallet_id: uuid.UUID = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    transaction_type: TransactionType | None = Query(None),
    file_format: str = Query("csv", pattern="^(csv|pdf)$", alias="format"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    request = StatementRequest(
        wallet_id=wallet_id, date_from=date_from, date_to=date_to, transaction_type=transaction_type
    )
    export_format = ExportFormat.PDF if file_format == "pdf" else ExportFormat.CSV
    _job, content, meta = StatementService(db).generate_and_log(current_user.id, request, export_format)
    media_type, filename = meta.split("|", 1)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/history", response_model=list[ExportJobPublic])
def list_statement_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExportJobPublic]:
    jobs = StatementService(db).list_history(current_user.id)
    return [ExportJobPublic.model_validate(job, from_attributes=True) for job in jobs]


@router.get("/history/{job_id}/download")
def download_statement_export(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    _job, content, meta = StatementService(db).download_job(current_user.id, job_id)
    media_type, filename = meta.split("|", 1)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
