"""FX quoting endpoints. `convert()` isn't exposed standalone — a quote is
consumed by TransactionService when it executes a cross-currency transfer."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.fx.schemas import FXQuotePublic, FXQuoteRequest
from app.fx.service import FXService
from app.users.models import User

router = APIRouter(prefix="/fx", tags=["fx"])


@router.post("/quote", response_model=FXQuotePublic, status_code=201)
def create_quote(
    payload: FXQuoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FXQuotePublic:
    quote = FXService(db).get_quote(current_user.id, payload)
    db.commit()
    return quote


@router.get("/quote/{quote_id}", response_model=FXQuotePublic)
def get_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FXQuotePublic:
    return FXService(db).get_valid_quote_for_user(current_user.id, quote_id)
