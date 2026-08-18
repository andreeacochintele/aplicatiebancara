"""Payments endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.fx.schemas import FXQuotePublic
from app.payments.schemas import (
    BeneficiaryCreate,
    BeneficiaryPublic,
    BeneficiaryUpdate,
    IbanTransferCreate,
    IbanTransferQuoteCreate,
    PaymentRequestCreate,
    PaymentRequestPay,
    PaymentRequestPublic,
    PhoneLookupRequest,
    PhoneRecipientPreview,
    PhoneTransferCreate,
    ScheduledPaymentCreate,
    ScheduledPaymentPublic,
    ScheduledPaymentUpdate,
)
from app.payments.service import (
    BeneficiaryService,
    IbanTransferService,
    PaymentRequestService,
    PhonePaymentService,
    ScheduledPaymentService,
)
from app.transactions.schemas import TransactionPublic
from app.users.models import User

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/transfers/iban/fx-quote", response_model=FXQuotePublic, status_code=status.HTTP_201_CREATED)
def create_iban_transfer_fx_quote(
    payload: IbanTransferQuoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FXQuotePublic:
    quote = IbanTransferService(db).create_iban_fx_quote(current_user.id, payload)
    db.commit()
    return quote


@router.post("/transfers/iban", response_model=TransactionPublic, status_code=status.HTTP_201_CREATED)
def create_iban_transfer(
    payload: IbanTransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    transaction = IbanTransferService(db).create_iban_transfer(current_user.id, payload)
    db.commit()
    return transaction


@router.post("/phone/lookup", response_model=PhoneRecipientPreview)
def lookup_phone_recipient(
    payload: PhoneLookupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PhoneRecipientPreview:
    return PhonePaymentService(db).lookup_recipient(current_user.id, payload.phone)


@router.post("/phone/transfer", response_model=TransactionPublic, status_code=status.HTTP_201_CREATED)
def create_phone_transfer(
    payload: PhoneTransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    transaction = PhonePaymentService(db).create_phone_transfer(current_user.id, payload)
    db.commit()
    return transaction


@router.post("/payment-requests", response_model=PaymentRequestPublic, status_code=status.HTTP_201_CREATED)
def create_payment_request(
    payload: PaymentRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentRequestPublic:
    payment_request = PaymentRequestService(db).create_payment_request(current_user.id, payload)
    db.commit()
    return payment_request


@router.get("/payment-requests/{request_id}", response_model=PaymentRequestPublic)
def get_payment_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentRequestPublic:
    return PaymentRequestService(db).get_active_payment_request(request_id)


@router.post("/payment-requests/{request_id}/pay", response_model=TransactionPublic, status_code=status.HTTP_201_CREATED)
def pay_payment_request(
    request_id: uuid.UUID,
    payload: PaymentRequestPay,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPublic:
    transaction = PaymentRequestService(db).pay_payment_request(current_user.id, request_id, payload)
    db.commit()
    return transaction


@router.get("/scheduled-payments", response_model=list[ScheduledPaymentPublic])
def list_scheduled_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScheduledPaymentPublic]:
    return ScheduledPaymentService(db).list_scheduled_payments(current_user.id)


@router.post("/scheduled-payments", response_model=ScheduledPaymentPublic, status_code=status.HTTP_201_CREATED)
def create_scheduled_payment(
    payload: ScheduledPaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduledPaymentPublic:
    scheduled_payment = ScheduledPaymentService(db).create_scheduled_payment(current_user.id, payload)
    db.commit()
    return scheduled_payment


@router.get("/scheduled-payments/{scheduled_payment_id}", response_model=ScheduledPaymentPublic)
def get_scheduled_payment(
    scheduled_payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduledPaymentPublic:
    return ScheduledPaymentService(db).get_scheduled_payment(current_user.id, scheduled_payment_id)


@router.patch("/scheduled-payments/{scheduled_payment_id}", response_model=ScheduledPaymentPublic)
def update_scheduled_payment(
    scheduled_payment_id: uuid.UUID,
    payload: ScheduledPaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduledPaymentPublic:
    scheduled_payment = ScheduledPaymentService(db).update_scheduled_payment(
        current_user.id,
        scheduled_payment_id,
        payload,
    )
    db.commit()
    return scheduled_payment


@router.delete("/scheduled-payments/{scheduled_payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheduled_payment(
    scheduled_payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    ScheduledPaymentService(db).delete_scheduled_payment(current_user.id, scheduled_payment_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/beneficiaries", response_model=list[BeneficiaryPublic])
def list_beneficiaries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BeneficiaryPublic]:
    return BeneficiaryService(db).list_beneficiaries(current_user.id)


@router.post("/beneficiaries", response_model=BeneficiaryPublic, status_code=status.HTTP_201_CREATED)
def create_beneficiary(
    payload: BeneficiaryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BeneficiaryPublic:
    beneficiary = BeneficiaryService(db).create_beneficiary(current_user.id, payload)
    db.commit()
    return beneficiary


@router.get("/beneficiaries/{beneficiary_id}", response_model=BeneficiaryPublic)
def get_beneficiary(
    beneficiary_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BeneficiaryPublic:
    return BeneficiaryService(db).get_beneficiary(current_user.id, beneficiary_id)


@router.patch("/beneficiaries/{beneficiary_id}", response_model=BeneficiaryPublic)
def update_beneficiary(
    beneficiary_id: uuid.UUID,
    payload: BeneficiaryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BeneficiaryPublic:
    beneficiary = BeneficiaryService(db).update_beneficiary(current_user.id, beneficiary_id, payload)
    db.commit()
    return beneficiary


@router.delete("/beneficiaries/{beneficiary_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_beneficiary(
    beneficiary_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    BeneficiaryService(db).delete_beneficiary(current_user.id, beneficiary_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def not_implemented() -> dict:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="'payments' module is not implemented yet (Phase 1 skeleton only)",
    )
