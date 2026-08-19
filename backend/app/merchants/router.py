"""Merchant catalog and cashback-offer endpoints (architecture.md §11)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.merchants.schemas import (
    CashbackOfferCreate,
    CashbackOfferPublic,
    MerchantCreate,
    MerchantPublic,
    PurchaseResult,
)
from app.merchants.service import MerchantService
from app.users.models import User

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.get("", response_model=list[MerchantPublic])
def list_merchants(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MerchantPublic]:
    return MerchantService(db).list_merchants()


@router.get("/{merchant_id}", response_model=MerchantPublic)
def get_merchant(
    merchant_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MerchantPublic:
    return MerchantService(db).get_merchant(merchant_id)


@router.post("", response_model=MerchantPublic, status_code=201)
def create_merchant(
    payload: MerchantCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MerchantPublic:
    merchant = MerchantService(db).create_merchant(payload)
    db.commit()
    return merchant


@router.post("/{merchant_id}/cashback-offers", response_model=CashbackOfferPublic, status_code=201)
def create_cashback_offer(
    merchant_id: uuid.UUID,
    payload: CashbackOfferCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CashbackOfferPublic:
    offer = MerchantService(db).create_cashback_offer(merchant_id, payload)
    db.commit()
    return offer


@router.post("/sync-rewards", response_model=list[PurchaseResult])
def sync_rewards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PurchaseResult]:
    """Scan the caller's own completed card payments and award reward points
    for any merchant-matched ones not yet credited. No client-supplied
    amount — points are derived only from real transactions."""
    results = MerchantService(db).sync_purchases_from_transactions(current_user.id)
    db.commit()
    return results
