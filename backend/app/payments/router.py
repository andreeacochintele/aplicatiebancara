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
    BillSplitCreate,
    BillSplitPay,
    BillSplitPublic,
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
    TransactionFolderAddTransaction,
    TransactionFolderCreate,
    TransactionFolderPublic,
    TransactionFolderUpdate,
)
from app.payments.service import (
    BeneficiaryService,
    BillSplitService,
    IbanTransferService,
    PaymentRequestService,
    PhonePaymentService,
    ScheduledPaymentService,
    TransactionFolderService,
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


@router.get("/payment-requests", response_model=list[PaymentRequestPublic])
def list_payment_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PaymentRequestPublic]:
    return PaymentRequestService(db).list_created_by_user(current_user.id)


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


@router.patch("/payment-requests/{request_id}/cancel", response_model=PaymentRequestPublic)
def cancel_payment_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentRequestPublic:
    payment_request = PaymentRequestService(db).cancel_payment_request(current_user.id, request_id)
    db.commit()
    return payment_request


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


@router.get("/bill-splits", response_model=list[BillSplitPublic])
def list_bill_splits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BillSplitPublic]:
    return BillSplitService(db).list_bill_splits(current_user.id)


@router.post("/bill-splits", response_model=BillSplitPublic, status_code=status.HTTP_201_CREATED)
def create_bill_split(
    payload: BillSplitCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillSplitPublic:
    bill_split = BillSplitService(db).create_bill_split(current_user.id, payload)
    db.commit()
    return bill_split


@router.get("/bill-splits/{bill_split_id}", response_model=BillSplitPublic)
def get_bill_split(
    bill_split_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillSplitPublic:
    return BillSplitService(db).get_bill_split(current_user.id, bill_split_id)


@router.patch("/bill-splits/{bill_split_id}/cancel", response_model=BillSplitPublic)
def cancel_bill_split(
    bill_split_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillSplitPublic:
    bill_split = BillSplitService(db).cancel_bill_split(current_user.id, bill_split_id)
    db.commit()
    return bill_split


@router.post("/bill-splits/{bill_split_id}/participants/{participant_id}/pay", response_model=BillSplitPublic)
def pay_bill_split_participant(
    bill_split_id: uuid.UUID,
    participant_id: uuid.UUID,
    payload: BillSplitPay,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillSplitPublic:
    bill_split = BillSplitService(db).pay_participant(current_user.id, bill_split_id, participant_id, payload)
    db.commit()
    return bill_split


@router.post("/bill-splits/{bill_split_id}/participants/{participant_id}/decline", response_model=BillSplitPublic)
def decline_bill_split_participant(
    bill_split_id: uuid.UUID,
    participant_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillSplitPublic:
    bill_split = BillSplitService(db).decline_participant(current_user.id, bill_split_id, participant_id)
    db.commit()
    return bill_split


@router.get("/transaction-folders", response_model=list[TransactionFolderPublic])
def list_transaction_folders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionFolderPublic]:
    return TransactionFolderService(db).list_folders(current_user.id)


@router.post("/transaction-folders", response_model=TransactionFolderPublic, status_code=status.HTTP_201_CREATED)
def create_transaction_folder(
    payload: TransactionFolderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionFolderPublic:
    folder = TransactionFolderService(db).create_folder(current_user.id, payload)
    db.commit()
    return folder


@router.get("/transaction-folders/{folder_id}", response_model=TransactionFolderPublic)
def get_transaction_folder(
    folder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionFolderPublic:
    return TransactionFolderService(db).get_folder(current_user.id, folder_id)


@router.patch("/transaction-folders/{folder_id}", response_model=TransactionFolderPublic)
def update_transaction_folder(
    folder_id: uuid.UUID,
    payload: TransactionFolderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionFolderPublic:
    folder = TransactionFolderService(db).update_folder(current_user.id, folder_id, payload)
    db.commit()
    return folder


@router.delete("/transaction-folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction_folder(
    folder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    TransactionFolderService(db).delete_folder(current_user.id, folder_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/transaction-folders/{folder_id}/transactions", response_model=TransactionFolderPublic)
def add_transaction_to_folder(
    folder_id: uuid.UUID,
    payload: TransactionFolderAddTransaction,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionFolderPublic:
    folder = TransactionFolderService(db).add_transaction(current_user.id, folder_id, payload.transaction_id)
    db.commit()
    return folder


@router.delete("/transaction-folders/{folder_id}/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_transaction_from_folder(
    folder_id: uuid.UUID,
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    TransactionFolderService(db).remove_transaction(current_user.id, folder_id, transaction_id)
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
