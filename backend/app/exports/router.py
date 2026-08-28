"""Business transaction export (architecture.md §25): a filtered preview and
CSV/XLSX download of the current business user's own transaction activity,
gated to business accounts via require_business, same shape as require_admin.
Every generated export is logged so it shows up in export history."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_business
from app.database import get_db
from app.exports.models import ExportFormat
from app.exports.schemas import ExportFileFormat, ExportJobPublic, TransactionExportPreview, TransactionExportRequest
from app.exports.service import ExportService
from app.transactions.models import TransactionStatus
from app.users.models import User

router = APIRouter(prefix="/exports", tags=["exports"])


def _build_request(
    date_from: date,
    date_to: date,
    wallet_id: uuid.UUID | None,
    currency: str | None,
    direction,
    status: TransactionStatus | None,
    category_id: uuid.UUID | None,
) -> TransactionExportRequest:
    return TransactionExportRequest(
        date_from=date_from,
        date_to=date_to,
        wallet_id=wallet_id,
        currency=currency,
        direction=direction,
        status=status,
        category_id=category_id,
    )


@router.get("/preview", response_model=TransactionExportPreview)
def preview_export(
    date_from: date = Query(...),
    date_to: date = Query(...),
    wallet_id: uuid.UUID | None = Query(None),
    currency: str | None = Query(None),
    direction: str | None = Query(None),
    status: TransactionStatus | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
) -> TransactionExportPreview:
    request = _build_request(date_from, date_to, wallet_id, currency, direction, status, category_id)
    return ExportService(db).build_preview(current_user.id, request)


@router.get("/transactions")
def export_transactions(
    date_from: date = Query(...),
    date_to: date = Query(...),
    wallet_id: uuid.UUID | None = Query(None),
    currency: str | None = Query(None),
    direction: str | None = Query(None),
    status: TransactionStatus | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    format: ExportFileFormat = Query("csv"),
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
) -> Response:
    request = _build_request(date_from, date_to, wallet_id, currency, direction, status, category_id)
    file_format = {
        "xlsx": ExportFormat.XLSX,
        "pdf": ExportFormat.PDF,
        "mt940": ExportFormat.MT940,
    }.get(format, ExportFormat.CSV)
    _job, content, meta = ExportService(db).generate_and_log(current_user.id, request, file_format)
    media_type, filename = meta.split("|", 1)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=list[ExportJobPublic])
def list_export_history(
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
) -> list[ExportJobPublic]:
    return ExportService(db).list_history(current_user.id)


@router.get("/{job_id}/download")
def download_export(
    job_id: uuid.UUID,
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
) -> Response:
    _job, content, meta = ExportService(db).download_job(current_user.id, job_id)
    media_type, filename = meta.split("|", 1)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
