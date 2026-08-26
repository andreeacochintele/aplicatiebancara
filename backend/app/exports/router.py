"""Business transaction export (architecture.md §25): filtered CSV of the
current business user's own transaction activity. Gated to business accounts
via require_business, same shape as require_admin."""
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_business
from app.database import get_db
from app.exports.schemas import TransactionExportRequest
from app.exports.service import ExportService
from app.transactions.models import TransactionStatus
from app.users.models import User

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/transactions")
def export_transactions(
    date_from: date = Query(...),
    date_to: date = Query(...),
    wallet_id: uuid.UUID | None = Query(None),
    currency: str | None = Query(None),
    direction: Literal["incoming", "outgoing"] | None = Query(None),
    status: TransactionStatus | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_business),
    db: Session = Depends(get_db),
) -> Response:
    request = TransactionExportRequest(
        date_from=date_from,
        date_to=date_to,
        wallet_id=wallet_id,
        currency=currency,
        direction=direction,
        status=status,
        category_id=category_id,
    )
    service = ExportService(db)
    transactions = service.list_transactions(current_user.id, request)
    content = service.to_csv(transactions).encode("utf-8")
    filename = f"transactions_{date_from}_{date_to}.csv"

    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
