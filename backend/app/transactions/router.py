"""Transaction endpoints. `POST /transactions/transfer` is the reference
deterministic internal-transfer flow (architecture.md's Phase 1 end-to-end goal)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.transactions.schemas import (
    CardPaymentCreate,
    CardTopUpCreate,
    CreditCardRepaymentCreate,
    InternalTransferCreate,
    TransactionPublic,
)
from app.transactions.service import TransactionService
from app.users.models import User

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionPublic])
def list_my_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionPublic]:
    return TransactionService(db).list_for_user(current_user.id)


@router.get("/{transaction_id}", response_model=TransactionPublic)
def get_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    return TransactionService(db).get_for_user(current_user.id, transaction_id)


@router.post("/transfer", response_model=TransactionPublic, status_code=201)
def create_transfer(
    payload: InternalTransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    transaction = TransactionService(db).create_internal_transfer(current_user.id, payload)
    db.commit()
    return transaction


@router.post("/card-payment", response_model=TransactionPublic, status_code=201)
def create_card_payment(
    payload: CardPaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    transaction = TransactionService(db).create_card_payment(current_user.id, payload)
    db.commit()
    return transaction


@router.post("/credit-card-repayment", response_model=TransactionPublic, status_code=201)
def create_credit_card_repayment(
    payload: CreditCardRepaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    transaction = TransactionService(db).create_credit_card_repayment(current_user.id, payload)
    db.commit()
    return transaction


@router.post("/top-up", response_model=TransactionPublic, status_code=201)
def create_card_top_up(
    payload: CardTopUpCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    transaction = TransactionService(db).create_card_top_up(current_user.id, payload)
    db.commit()
    return transaction
