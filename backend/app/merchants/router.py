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
    PurchaseCreate,
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


@router.post("/{merchant_id}/purchases", response_model=PurchaseResult, status_code=201)
def record_purchase(
    merchant_id: uuid.UUID,
    payload: PurchaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PurchaseResult:
    result = MerchantService(db).record_purchase(current_user.id, merchant_id, payload)
    db.commit()
    return result
