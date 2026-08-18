"""Beneficiary business rules for the payments module."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_UP, Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.fx.models import FXQuote
from app.fx.schemas import FXQuoteRequest
from app.fx.service import FEE_RATE, FXService
from app.payments.models import (
    Beneficiary,
    PaymentRequest,
    PaymentRequestStatus,
    ScheduledPayment,
    ScheduledPaymentStatus,
)
from app.payments.repository import BeneficiaryRepository, PaymentRequestRepository, ScheduledPaymentRepository
from app.payments.schemas import (
    BeneficiaryCreate,
    BeneficiaryUpdate,
    IbanTransferCreate,
    IbanTransferQuoteCreate,
    PaymentRequestCreate,
    PaymentRequestPay,
    PhoneRecipientPreview,
    PhoneTransferCreate,
    ScheduledPaymentCreate,
    ScheduledPaymentUpdate,
)
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.repository import UserRepository
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository


_CENTS = Decimal("0.01")
_SCHEDULED_STATUS_TRANSITIONS: dict[ScheduledPaymentStatus, set[ScheduledPaymentStatus]] = {
    ScheduledPaymentStatus.ACTIVE: {ScheduledPaymentStatus.PAUSED, ScheduledPaymentStatus.CANCELLED},
    ScheduledPaymentStatus.PAUSED: {ScheduledPaymentStatus.ACTIVE, ScheduledPaymentStatus.CANCELLED},
    ScheduledPaymentStatus.CANCELLED: set(),
}


class BeneficiaryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = BeneficiaryRepository(db)
        self.users = UserRepository(db)

    def create_beneficiary(self, owner_user_id: uuid.UUID, data: BeneficiaryCreate) -> Beneficiary:
        if data.beneficiary_user_id is not None and self.users.get_by_id(data.beneficiary_user_id) is None:
            raise NotFoundError("Beneficiary user not found")

        beneficiary = Beneficiary(
            owner_user_id=owner_user_id,
            beneficiary_user_id=data.beneficiary_user_id,
            name=data.name,
            iban=data.iban,
            phone=data.phone,
            is_favorite=data.is_favorite,
        )
        return self.repository.add(beneficiary)

    def list_beneficiaries(self, owner_user_id: uuid.UUID) -> list[Beneficiary]:
        return self.repository.list_for_owner(owner_user_id)

    def get_beneficiary(self, owner_user_id: uuid.UUID, beneficiary_id: uuid.UUID) -> Beneficiary:
        beneficiary = self.repository.get_owned_by_id(owner_user_id, beneficiary_id)
        if beneficiary is None:
            raise NotFoundError("Beneficiary not found")
        return beneficiary

    def update_beneficiary(
        self,
        owner_user_id: uuid.UUID,
        beneficiary_id: uuid.UUID,
        data: BeneficiaryUpdate,
    ) -> Beneficiary:
        beneficiary = self.get_beneficiary(owner_user_id, beneficiary_id)
        changes = data.model_dump(exclude_unset=True)

        if "beneficiary_user_id" in changes and changes["beneficiary_user_id"] is not None:
            if self.users.get_by_id(changes["beneficiary_user_id"]) is None:
                raise NotFoundError("Beneficiary user not found")

        proposed_user_id = changes.get("beneficiary_user_id", beneficiary.beneficiary_user_id)
        proposed_iban = changes.get("iban", beneficiary.iban)
        proposed_phone = changes.get("phone", beneficiary.phone)
        if not any([proposed_user_id, proposed_iban, proposed_phone]):
            raise ValidationError("Beneficiary requires beneficiary_user_id, iban or phone")

        for field, value in changes.items():
            setattr(beneficiary, field, value)

        self.db.flush()
        return beneficiary

    def delete_beneficiary(self, owner_user_id: uuid.UUID, beneficiary_id: uuid.UUID) -> None:
        beneficiary = self.get_beneficiary(owner_user_id, beneficiary_id)
        self.repository.delete(beneficiary)


class IbanTransferService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.beneficiaries = BeneficiaryRepository(db)
        self.fx = FXService(db)
        self.transactions = TransactionService(db)
        self.wallets = WalletRepository(db)

    def create_iban_fx_quote(self, initiator_user_id: uuid.UUID, data: IbanTransferQuoteCreate) -> FXQuote:
        source = self._get_owned_source_wallet(initiator_user_id, data.source_wallet_id)
        target_currency = data.currency.upper()
        if source.currency == target_currency:
            raise ValidationError("FX quote is not required for same-currency transfers")

        rate = self.fx.get_rate(source.currency, target_currency)
        source_amount = self._source_amount_for_target(data.amount, rate)
        quote = self.fx.get_quote(
            initiator_user_id,
            FXQuoteRequest(
                source_currency=source.currency,
                target_currency=target_currency,
                source_amount=source_amount,
            ),
        )
        if quote.target_amount < data.amount:
            raise ValidationError("Could not produce an FX quote for this target amount")
        return quote

    def create_iban_transfer(self, initiator_user_id: uuid.UUID, data: IbanTransferCreate) -> Transaction:
        source = self._get_owned_source_wallet(initiator_user_id, data.source_wallet_id)

        currency = data.currency.upper()
        if source.currency == currency:
            debit_amount = data.amount
            quote: FXQuote | None = None
        else:
            if data.fx_quote_id is None:
                raise ValidationError("Cross-currency IBAN transfers require an fx_quote_id")
            quote = self.fx.get_valid_quote_for_user(initiator_user_id, data.fx_quote_id)
            if quote.source_currency != source.currency or quote.target_currency != currency:
                raise ValidationError("FX quote currencies don't match the selected transfer")
            if quote.target_amount != data.amount:
                raise ValidationError("Transfer amount doesn't match the quoted target amount")
            debit_amount = quote.source_amount

        if source.available_balance < debit_amount:
            raise ConflictError("Insufficient available balance")

        description = data.description or f"Transfer to {data.beneficiary_name} - {data.iban}"
        transaction = self.transactions.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=source.id,
                destination_wallet_id=None,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.PROCESSING,
                amount=data.amount,
                currency=currency,
                source_amount=quote.source_amount if quote is not None else None,
                source_currency=quote.source_currency if quote is not None else None,
                exchange_rate=quote.exchange_rate if quote is not None else None,
                fx_quote_id=quote.id if quote is not None else None,
                description=description,
                processed_at=datetime.now(timezone.utc),
            )
        )
        source.available_balance -= debit_amount
        self.transactions.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=source.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=debit_amount,
                currency=source.currency,
                balance_after=source.available_balance,
            )
        )
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)
        if quote is not None:
            self.fx.mark_accepted(quote)

        if data.save_beneficiary:
            self.beneficiaries.add(
                Beneficiary(
                    owner_user_id=initiator_user_id,
                    name=data.beneficiary_name,
                    iban=data.iban,
                    is_favorite=data.is_favorite,
                )
            )

        self.db.flush()
        return transaction

    def _get_owned_source_wallet(self, initiator_user_id: uuid.UUID, wallet_id: uuid.UUID) -> Wallet:
        source = self.wallets.get_by_id(wallet_id)
        if source is None:
            raise NotFoundError("Source wallet not found")
        if source.user_id != initiator_user_id:
            raise ValidationError("Source wallet does not belong to the initiating user")
        return source

    def _source_amount_for_target(self, target_amount: Decimal, rate: Decimal) -> Decimal:
        estimated = (target_amount / (rate * (Decimal("1") - FEE_RATE))).quantize(_CENTS, rounding=ROUND_UP)
        return estimated


class ScheduledPaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ScheduledPaymentRepository(db)
        self.wallets = WalletRepository(db)

    def create_scheduled_payment(self, owner_user_id: uuid.UUID, data: ScheduledPaymentCreate) -> ScheduledPayment:
        self._validate_source_wallet(owner_user_id, data.source_wallet_id, data.currency)
        scheduled_payment = ScheduledPayment(
            owner_user_id=owner_user_id,
            source_wallet_id=data.source_wallet_id,
            beneficiary_name=data.beneficiary_name,
            iban=data.iban,
            amount=data.amount,
            currency=data.currency.upper(),
            frequency=data.frequency,
            next_run_on=data.next_run_on,
            notify_days_before=data.notify_days_before,
            status=ScheduledPaymentStatus.ACTIVE,
            description=data.description,
        )
        return self.repository.add(scheduled_payment)

    def list_scheduled_payments(self, owner_user_id: uuid.UUID) -> list[ScheduledPayment]:
        return self.repository.list_for_owner(owner_user_id)

    def get_scheduled_payment(self, owner_user_id: uuid.UUID, scheduled_payment_id: uuid.UUID) -> ScheduledPayment:
        scheduled_payment = self.repository.get_owned_by_id(owner_user_id, scheduled_payment_id)
        if scheduled_payment is None:
            raise NotFoundError("Scheduled payment not found")
        return scheduled_payment

    def update_scheduled_payment(
        self,
        owner_user_id: uuid.UUID,
        scheduled_payment_id: uuid.UUID,
        data: ScheduledPaymentUpdate,
    ) -> ScheduledPayment:
        scheduled_payment = self.get_scheduled_payment(owner_user_id, scheduled_payment_id)
        if scheduled_payment.status == ScheduledPaymentStatus.CANCELLED:
            raise ConflictError("Cancelled scheduled payments cannot be updated")

        changes = data.model_dump(exclude_unset=True)
        requested_status = changes.pop("status", None)
        if requested_status is not None:
            self._transition_status(scheduled_payment, requested_status)

        source_wallet_id = changes.get("source_wallet_id", scheduled_payment.source_wallet_id)
        currency = changes.get("currency", scheduled_payment.currency)
        self._validate_source_wallet(owner_user_id, source_wallet_id, currency)

        for field, value in changes.items():
            if field == "currency" and value is not None:
                value = value.upper()
            setattr(scheduled_payment, field, value)

        self.db.flush()
        return scheduled_payment

    def delete_scheduled_payment(self, owner_user_id: uuid.UUID, scheduled_payment_id: uuid.UUID) -> None:
        scheduled_payment = self.get_scheduled_payment(owner_user_id, scheduled_payment_id)
        self.repository.delete(scheduled_payment)

    def _validate_source_wallet(self, owner_user_id: uuid.UUID, source_wallet_id: uuid.UUID, currency: str) -> Wallet:
        source = self.wallets.get_by_id(source_wallet_id)
        if source is None:
            raise NotFoundError("Source wallet not found")
        if source.user_id != owner_user_id:
            raise ValidationError("Source wallet does not belong to the current user")
        if source.currency != currency.upper():
            raise ValidationError("Scheduled payments currently require a source wallet in the payment currency")
        return source

    def _transition_status(self, scheduled_payment: ScheduledPayment, next_status: ScheduledPaymentStatus) -> None:
        if next_status == scheduled_payment.status:
            return
        allowed = _SCHEDULED_STATUS_TRANSITIONS[scheduled_payment.status]
        if next_status not in allowed:
            raise ConflictError(
                f"Cannot move scheduled payment from {scheduled_payment.status.value} to {next_status.value}"
            )
        scheduled_payment.status = next_status


class PhonePaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.wallets = WalletRepository(db)
        self.transactions = TransactionService(db)

    def lookup_recipient(self, initiator_user_id: uuid.UUID, phone: str) -> PhoneRecipientPreview:
        recipient = self.users.get_by_phone(phone)
        if recipient is None:
            raise NotFoundError("User with this phone number was not found")
        if recipient.id == initiator_user_id:
            raise ValidationError("Cannot send a phone transfer to yourself")

        wallet = self._get_main_wallet(recipient.id)
        if wallet is None:
            raise NotFoundError("Recipient has no destination wallet")

        return PhoneRecipientPreview(
            user_id=recipient.id,
            first_name=recipient.first_name,
            last_name=recipient.last_name,
            phone=recipient.phone or phone,
            destination_wallet_id=wallet.id,
            destination_wallet_currency=wallet.currency,
        )

    def create_phone_transfer(self, initiator_user_id: uuid.UUID, data: PhoneTransferCreate) -> Transaction:
        recipient = self.users.get_by_phone(data.phone)
        if recipient is None:
            raise NotFoundError("User with this phone number was not found")
        if recipient.id == initiator_user_id:
            raise ValidationError("Cannot send a phone transfer to yourself")

        source = self.wallets.get_by_id(data.source_wallet_id)
        if source is None or source.user_id != initiator_user_id:
            raise ValidationError("Source wallet does not belong to the initiating user")

        destination = self.wallets.get_by_user_and_currency(recipient.id, source.currency)
        if destination is None:
            raise NotFoundError(f"Recipient has no {source.currency} wallet")

        description = data.description or f"Phone transfer to {recipient.first_name} {recipient.last_name}"
        return self.transactions.create_internal_transfer(
            initiator_user_id,
            InternalTransferCreate(
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                amount=data.amount,
                description=description,
            ),
        )

    def _get_main_wallet(self, user_id: uuid.UUID) -> Wallet | None:
        wallets = self.wallets.list_for_user(user_id)
        return next((wallet for wallet in wallets if wallet.is_main), wallets[0] if wallets else None)


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class PaymentRequestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = PaymentRequestRepository(db)
        self.wallets = WalletRepository(db)
        self.transactions = TransactionService(db)

    def create_payment_request(self, creator_user_id: uuid.UUID, data: PaymentRequestCreate) -> PaymentRequest:
        destination = self.wallets.get_by_id(data.destination_wallet_id)
        if destination is None:
            raise NotFoundError("Destination wallet not found")
        if destination.user_id != creator_user_id:
            raise ValidationError("Destination wallet does not belong to the current user")

        currency = data.currency.upper()
        if currency != destination.currency:
            raise ValidationError("Payment request currency must match the destination wallet")

        payment_request = PaymentRequest(
            creator_user_id=creator_user_id,
            destination_wallet_id=destination.id,
            amount=data.amount,
            currency=currency,
            status=PaymentRequestStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=data.expires_in_minutes),
        )
        return self.repository.add(payment_request)

    def get_active_payment_request(self, request_id: uuid.UUID) -> PaymentRequest:
        payment_request = self.repository.get_by_id(request_id)
        if payment_request is None:
            raise NotFoundError("Payment request not found")
        self._ensure_active(payment_request)
        return payment_request

    def pay_payment_request(
        self,
        payer_user_id: uuid.UUID,
        request_id: uuid.UUID,
        data: PaymentRequestPay,
    ) -> Transaction:
        payment_request = self.get_active_payment_request(request_id)
        destination = self.wallets.get_by_id(payment_request.destination_wallet_id)
        if destination is None:
            raise NotFoundError("Destination wallet not found")
        if destination.user_id == payer_user_id:
            raise ValidationError("Cannot pay your own payment request")

        amount = payment_request.amount if payment_request.amount is not None else data.amount
        if amount is None:
            raise ValidationError("Amount is required for open payment requests")
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")

        source = self.wallets.get_by_id(data.source_wallet_id)
        if source is None or source.user_id != payer_user_id:
            raise ValidationError("Source wallet does not belong to the paying user")
        if source.currency != payment_request.currency:
            raise ValidationError("Source wallet currency must match the payment request currency")

        transaction = self.transactions.create_internal_transfer(
            payer_user_id,
            InternalTransferCreate(
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                amount=amount,
                description=data.description or f"QR payment request {payment_request.id}",
            ),
        )
        payment_request.status = PaymentRequestStatus.PAID
        self.db.flush()
        return transaction

    def _ensure_active(self, payment_request: PaymentRequest) -> None:
        if payment_request.status != PaymentRequestStatus.ACTIVE:
            raise ConflictError(f"Payment request is {payment_request.status.value}")
        if _as_aware_utc(payment_request.expires_at) < datetime.now(timezone.utc):
            payment_request.status = PaymentRequestStatus.EXPIRED
            raise ConflictError("Payment request has expired")
