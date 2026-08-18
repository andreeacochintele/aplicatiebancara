"""Statement endpoints (architecture.md §24): a JSON preview and a CSV/PDF
export of a wallet's activity over a period. Computed on demand from the
existing ledger — there is no dedicated statements table."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
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
    service = StatementService(db)
    statement = service.generate(current_user.id, request)

    filename = f"statement_{statement.currency}_{date_from}_{date_to}.{file_format}"
    if file_format == "csv":
        content: bytes = service.to_csv(statement).encode("utf-8")
        media_type = "text/csv"
    else:
        content = service.to_pdf(statement)
        media_type = "application/pdf"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
