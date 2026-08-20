"""Wallet endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.users.models import User
from app.wallets.schemas import WalletCreate, WalletPublic
from app.wallets.service import WalletService

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.get("", response_model=list[WalletPublic])
def list_my_wallets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WalletPublic]:
    return WalletService(db).list_wallets(current_user.id)


@router.post("", response_model=WalletPublic, status_code=201)
def create_wallet(
    payload: WalletCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletPublic:
    wallet = WalletService(db).create_wallet(current_user.id, payload)
    db.commit()
    return wallet


@router.patch("/{wallet_id}/set-main", response_model=WalletPublic)
def set_main_wallet(
    wallet_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletPublic:
    wallet = WalletService(db).set_main_wallet(current_user.id, wallet_id)
    db.commit()
    return wallet
