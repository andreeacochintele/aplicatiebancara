"""Beneficiary business rules for the payments module."""
import calendar
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_UP, Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.fraud.service import FraudService
from app.fx.models import FXQuote
from app.fx.schemas import FXQuoteRequest
from app.fx.service import FEE_RATE, FXService
from app.notifications.service import NotificationsService
from app.payments.models import (
    Beneficiary,
    BillSplit,
    BillSplitParticipant,
    BillSplitParticipantStatus,
    BillSplitStatus,
    BulkTransferTemplate,
    BulkTransferTemplateRow,
    PaymentRequest,
    PaymentRequestStatus,
    ScheduledPayment,
    ScheduledPaymentFrequency,
    ScheduledPaymentStatus,
    TransactionFolder,
    TransactionFolderItem,
)
from app.payments.repository import (
    BeneficiaryRepository,
    BillSplitRepository,
    BulkTransferTemplateRepository,
    PaymentRequestRepository,
    ScheduledPaymentRepository,
    TransactionFolderRepository,
)
from app.payments.schemas import (
    BeneficiaryCreate,
    BeneficiaryUpdate,
    BillSplitCreate,
    BillSplitParticipantCreate,
    BillSplitPay,
    BillSplitPublic,
    BulkTransferBatchSummary,
    BulkTransferCreate,
    BulkTransferResult,
    BulkTransferRow,
    BulkTransferRowResult,
    BulkTransferTemplateCreate,
    BulkTransferTemplatePublic,
    BulkTransferTemplateRowPublic,
    IbanTransferCreate,
    IbanTransferQuoteCreate,
    PaymentRequestCreate,
    PaymentRequestPay,
    PhoneRecipientPreview,
    PhoneTransferCreate,
    ScheduledPaymentCreate,
    ScheduledPaymentUpdate,
    TransactionFolderCreate,
    TransactionFolderPublic,
    TransactionFolderUpdate,
)
from app.supabase import is_supabase_session
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.schemas import InternalTransferCreate
from app.transactions.repository import TransactionRepository
from app.transactions.service import TransactionService
from app.users.repository import UserRepository
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")
_SCHEDULED_STATUS_TRANSITIONS: dict[ScheduledPaymentStatus, set[ScheduledPaymentStatus]] = {
    ScheduledPaymentStatus.ACTIVE: {ScheduledPaymentStatus.PAUSED, ScheduledPaymentStatus.CANCELLED},
    ScheduledPaymentStatus.PAUSED: {ScheduledPaymentStatus.ACTIVE, ScheduledPaymentStatus.CANCELLED},
    ScheduledPaymentStatus.CANCELLED: set(),
}


def _advance_by_frequency(current: date, frequency: ScheduledPaymentFrequency) -> date:
    """Same day-of-month clamping as the frontend calendar's own projection
    (PaymentsPage.tsx's matchesMonthlyInterval) — a 31st start still lands on
    Feb 28/29 rather than raising. ONCE is never passed here: run_now cancels
    a ONCE template instead of advancing it."""
    if frequency == ScheduledPaymentFrequency.WEEKLY:
        return current + timedelta(days=7)
    months = {
        ScheduledPaymentFrequency.MONTHLY: 1,
        ScheduledPaymentFrequency.QUARTERLY: 3,
        ScheduledPaymentFrequency.YEARLY: 12,
    }[frequency]
    total_month_index = current.month - 1 + months
    year = current.year + total_month_index // 12
    month = total_month_index % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

# Transfers, FX conversions, loan installments, and bill-split settlements
# aren't "a payment" in the sense either feature means it -- only an actual
# purchase (or a recurring payment executing as one) qualifies for splitting
# the bill with someone else.
SPLITTABLE_TRANSACTION_TYPES = {TransactionType.CARD_PAYMENT, TransactionType.SCHEDULED_PAYMENT}
# Folders additionally accept cashback, since grouping "this purchase and
# the cashback it earned" together is a real use case; transfers, FX, loans,
# and bill-split settlements still don't belong in a spending folder.
FOLDER_ELIGIBLE_TRANSACTION_TYPES = SPLITTABLE_TRANSACTION_TYPES | {TransactionType.CASHBACK}


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

        # Must match the rate get_quote() itself will price with below (now
        # the live rate, not the static table) — otherwise this estimate
        # under-shoots by the live margin and the quote it produces can land
        # short of the requested target amount.
        rate = self.fx.get_market_rate(source.currency, target_currency)
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

    def create_iban_transfer(
        self,
        initiator_user_id: uuid.UUID,
        data: IbanTransferCreate,
        *,
        batch_reference: str | None = None,
        batch_sibling_ids: frozenset[uuid.UUID] | None = None,
    ) -> Transaction:
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

        # On-us: the IBAN belongs to another EasyB wallet, so route through the
        # normal internal-transfer path (source debit + destination credit)
        # instead of treating it as money leaving the bank.
        destination = self.wallets.get_by_iban(data.iban)
        if destination is not None and destination.id == source.id:
            raise ValidationError("Cannot transfer to the same account")
        if destination is not None and destination.currency != currency:
            # Deliberately an error rather than a conversion. Whether the IBAN
            # is on-us is decided above, on its own; letting a currency
            # mismatch fall through to the external branch below would debit
            # the sender, set destination_wallet_id to NULL and mark the
            # transfer COMPLETED while the recipient — a real account on this
            # very system — is never credited. Same answer the phone-transfer
            # path already gives ("Recipient has no EUR wallet"); converting
            # instead would need an FX quote priced against the destination's
            # currency, which the sender has no way to ask for yet.
            raise ValidationError(
                f"This EasyB account holds {destination.currency}, not {currency}. "
                f"Send {destination.currency} instead, or ask the recipient to open "
                f"a {currency} account."
            )
        if destination is not None:
            transaction = self.transactions.create_internal_transfer(
                initiator_user_id,
                InternalTransferCreate(
                    source_wallet_id=source.id,
                    destination_wallet_id=destination.id,
                    amount=debit_amount,
                    fx_quote_id=data.fx_quote_id,
                    description=description,
                ),
                batch_reference=batch_reference,
                batch_sibling_ids=batch_sibling_ids,
            )
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
                batch_reference=batch_reference,
            )
        )
        # Money leaving the bank entirely, so this gets the same fraud seam
        # the internal-transfer path uses — scored before any balance moves.
        # A blocked transfer is HOLD'd and left PENDING_REVIEW by
        # FraudService; there's no destination wallet here, so approving it
        # later is just the DEBIT that FraudService.approve() already writes.
        if not FraudService(self.db).evaluate_transaction(
            transaction, source, batch_reference=batch_reference, batch_sibling_ids=batch_sibling_ids
        ).blocked:
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
        # Consumed either way: the held transaction already carries this
        # quote's priced amounts, and leaving it OPEN would let the same
        # pricing fund a second transfer while this one is under review.
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

    def create_bulk_transfer(self, initiator_user_id: uuid.UUID, data: BulkTransferCreate) -> BulkTransferResult:
        """Payroll-style batch: runs each row through create_iban_transfer
        independently, so one bad IBAN or an underfunded row doesn't sink the
        rest of the batch. Same-currency only (no FX) — a bulk run has one
        source wallet and one currency for every row; per-row FX quotes are
        out of scope. Each row gets its own savepoint (skipped on the
        Supabase REST backend, which has no local transaction to nest — same
        reasoning as MerchantService.sync_purchases_from_transactions) so a
        failed row's partial state can't leak into the next one.

        Every row shares one batch_reference, generated here — the only
        thing it does is tag whichever FraudCase(s) this batch's own
        screening creates, so the admin Fraud Review page can group and
        decide them together instead of one unrelated-looking case per row.

        Each row also gets the ids of every transaction this same call
        already created (batch_sibling_ids) — FraudService excludes those
        from HIGH_VELOCITY's count, so a batch's own rows don't rack up
        velocity against each other. A normal-sized payroll run no longer
        flags itself just for having several rows; a genuinely oversized
        amount, or unrelated activity around it, still can."""
        currency = data.currency.upper()
        use_savepoint = not is_supabase_session(self.db)
        batch_reference = str(uuid.uuid4())
        batch_transaction_ids: set[uuid.UUID] = set()
        results: list[BulkTransferRowResult] = []
        for row in data.rows:
            row_data = IbanTransferCreate(
                beneficiary_name=row.beneficiary_name,
                iban=row.iban,
                source_wallet_id=data.source_wallet_id,
                amount=row.amount,
                currency=currency,
                description=row.description,
                save_beneficiary=data.save_beneficiaries,
            )
            try:
                if use_savepoint:
                    with self.db.begin_nested():
                        transaction = self.create_iban_transfer(
                            initiator_user_id,
                            row_data,
                            batch_reference=batch_reference,
                            batch_sibling_ids=frozenset(batch_transaction_ids),
                        )
                else:
                    transaction = self.create_iban_transfer(
                        initiator_user_id,
                        row_data,
                        batch_reference=batch_reference,
                        batch_sibling_ids=frozenset(batch_transaction_ids),
                    )
            except (ValidationError, ConflictError, NotFoundError) as exc:
                results.append(
                    BulkTransferRowResult(
                        beneficiary_name=row.beneficiary_name,
                        iban=row.iban,
                        amount=row.amount,
                        error=str(exc),
                    )
                )
                continue
            batch_transaction_ids.add(transaction.id)
            results.append(
                BulkTransferRowResult(
                    beneficiary_name=row.beneficiary_name,
                    iban=row.iban,
                    amount=row.amount,
                    transaction_id=transaction.id,
                    status=transaction.status.value,
                )
            )

        succeeded = sum(1 for row in results if row.transaction_id is not None)
        return BulkTransferResult(succeeded=succeeded, failed=len(results) - succeeded, results=results)

    def list_bulk_transfer_batches(self, initiator_user_id: uuid.UUID) -> list[BulkTransferBatchSummary]:
        """Groups this user's own past bulk-transfer rows
        (Transaction.batch_reference, set only by create_bulk_transfer) into
        one summary per batch, newest first. Sourced from the same
        list_for_user window every other read in this module uses — deep
        history beyond that isn't in scope for a summary list."""
        transactions = [
            transaction
            for transaction in self.transactions.repository.list_for_user(initiator_user_id, limit=300)
            if transaction.batch_reference is not None and transaction.initiator_user_id == initiator_user_id
        ]
        grouped: dict[str, list[Transaction]] = {}
        for transaction in transactions:
            grouped.setdefault(transaction.batch_reference, []).append(transaction)

        summaries: list[BulkTransferBatchSummary] = []
        for reference, rows in grouped.items():
            earliest = min(row.created_at for row in rows)
            summaries.append(
                BulkTransferBatchSummary(
                    batch_reference=reference,
                    created_at=earliest,
                    currency=rows[0].currency,
                    total_amount=sum((row.amount for row in rows), Decimal("0")),
                    row_count=len(rows),
                    completed_count=sum(1 for row in rows if row.status == TransactionStatus.COMPLETED),
                    pending_review_count=sum(1 for row in rows if row.status == TransactionStatus.PENDING_REVIEW),
                    other_count=sum(
                        1
                        for row in rows
                        if row.status not in (TransactionStatus.COMPLETED, TransactionStatus.PENDING_REVIEW)
                    ),
                )
            )
        summaries.sort(key=lambda summary: summary.created_at, reverse=True)
        return summaries

    def list_bulk_transfer_batch_rows(self, initiator_user_id: uuid.UUID, batch_reference: str) -> list[Transaction]:
        """Individual transactions of one bulk-transfer batch, for the
        expand/collapse detail view on the batch history page. Same
        ownership + lookup window as list_bulk_transfer_batches, just
        filtered down to a single batch_reference instead of grouped."""
        rows = [
            transaction
            for transaction in self.transactions.repository.list_for_user(initiator_user_id, limit=300)
            if transaction.batch_reference == batch_reference and transaction.initiator_user_id == initiator_user_id
        ]
        rows.sort(key=lambda transaction: transaction.created_at)
        return rows

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
            reference=data.reference,
            note=data.note,
        )
        return self.repository.add(payment_request)

    def list_created_by_user(self, creator_user_id: uuid.UUID) -> list[PaymentRequest]:
        return self.repository.list_for_creator(creator_user_id)

    def cancel_payment_request(self, creator_user_id: uuid.UUID, request_id: uuid.UUID) -> PaymentRequest:
        payment_request = self.repository.get_owned_by_id(creator_user_id, request_id)
        if payment_request is None:
            raise NotFoundError("Payment request not found")
        if payment_request.status != PaymentRequestStatus.ACTIVE:
            raise ConflictError(f"Payment request is {payment_request.status.value}")
        payment_request.status = PaymentRequestStatus.CANCELLED
        self.db.flush()
        return payment_request

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
            # The request is marked PAID unconditionally just below, so a
            # fraud HOLD here would report a settled request whose money is
            # still frozen. Screening this flow needs that status handling
            # first — see create_internal_transfer's docstring.
            screen_for_fraud=False,
        )
        payment_request.status = PaymentRequestStatus.PAID
        self.db.flush()
        return transaction

    def _ensure_active(self, payment_request: PaymentRequest) -> None:
        if payment_request.status != PaymentRequestStatus.ACTIVE:
            raise ConflictError(f"Payment request is {payment_request.status.value}")
        if _as_aware_utc(payment_request.expires_at) < datetime.now(timezone.utc):
            payment_request.status = PaymentRequestStatus.EXPIRED
            # Must persist despite the ConflictError below aborting the
            # caller's own commit -- no service in this codebase otherwise
            # calls db.commit() (routers do, on success), but this status
            # transition needs to survive independent of the surrounding
            # request's failure. Safe here specifically because both call
            # sites (get_active_payment_request's GET route, and the start
            # of pay_payment_request) invoke this before any wallet
            # mutation is pending. Same pattern as FXService.get_valid_quote_for_user.
            self.db.commit()
            raise ConflictError("Payment request has expired")


class BillSplitService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = BillSplitRepository(db)
        self.transactions = TransactionRepository(db)
        self.transaction_service = TransactionService(db)
        self.users = UserRepository(db)
        self.wallets = WalletRepository(db)
        self.notifications = NotificationsService(db)

    def create_bill_split(self, owner_user_id: uuid.UUID, data: BillSplitCreate) -> BillSplitPublic:
        if data.source_transaction_id is not None:
            source_transaction = self.transactions.get_for_user(owner_user_id, data.source_transaction_id)
            if source_transaction is None:
                raise NotFoundError("Source transaction not found")
            if source_transaction.status != TransactionStatus.COMPLETED:
                raise ValidationError("Only completed transactions can be split")
            if source_transaction.type not in SPLITTABLE_TRANSACTION_TYPES:
                raise ValidationError("Only payments can be split")

        # Resolve every participant BEFORE writing anything: under the
        # Supabase REST backend, self.repository.add() is an immediate
        # INSERT with no surrounding transaction to roll back, so creating
        # the BillSplit row first and only then discovering a bad phone
        # number/user id left an orphaned, participant-less OPEN split
        # behind on every such failure.
        resolved_participants: list[tuple[BillSplitParticipantCreate, uuid.UUID | None]] = []
        for participant_data in data.participants:
            participant_user_id = participant_data.participant_user_id
            if participant_user_id is None and participant_data.phone is not None:
                participant_user = self.users.get_by_phone(participant_data.phone)
                if participant_user is None:
                    raise NotFoundError("User with this phone number was not found")
                participant_user_id = participant_user.id
            elif participant_user_id is not None:
                participant_user = self.users.get_by_id(participant_user_id)
                if participant_user is None:
                    raise NotFoundError("Participant user not found")

            if participant_user_id == owner_user_id:
                raise ValidationError("Bill split participant cannot be the owner")

            resolved_participants.append((participant_data, participant_user_id))

        bill_split = self.repository.add(
            BillSplit(
                owner_user_id=owner_user_id,
                source_transaction_id=data.source_transaction_id,
                title=data.title,
                total_amount=data.total_amount,
                currency=data.currency.upper(),
                status=BillSplitStatus.OPEN,
                description=data.description,
            )
        )

        for participant_data, participant_user_id in resolved_participants:
            self.repository.add_participant(
                BillSplitParticipant(
                    bill_split_id=bill_split.id,
                    participant_user_id=participant_user_id,
                    name=participant_data.name,
                    phone=participant_data.phone,
                    amount=participant_data.amount or Decimal("0"),
                    status=BillSplitParticipantStatus.PENDING,
                )
            )
            try:
                self.notifications.create(
                    participant_user_id,
                    type="SPLIT_BILL",
                    title="Split bill request",
                    message=f"You were asked to pay {participant_data.amount or Decimal('0')} {bill_split.currency} for '{bill_split.title}'.",
                )
            except Exception:
                logger.exception("Failed to notify split-bill participant %s", participant_user_id)

        self.db.flush()
        return self._to_public(bill_split)

    def list_bill_splits(self, user_id: uuid.UUID) -> list[BillSplitPublic]:
        bill_splits = self.repository.list_for_user(user_id)
        participants_by_split = self.repository.list_participants_for_splits([split.id for split in bill_splits])
        return [self._to_public(split, participants_by_split[split.id]) for split in bill_splits]

    def get_bill_split(self, user_id: uuid.UUID, bill_split_id: uuid.UUID) -> BillSplitPublic:
        return self._to_public(self._get_visible(user_id, bill_split_id))

    def cancel_bill_split(self, owner_user_id: uuid.UUID, bill_split_id: uuid.UUID) -> BillSplitPublic:
        bill_split = self._get_owned(owner_user_id, bill_split_id)
        if bill_split.status == BillSplitStatus.SETTLED:
            raise ConflictError("Settled bill splits cannot be cancelled")
        bill_split.status = BillSplitStatus.CANCELLED
        self.db.flush()
        return self._to_public(bill_split)

    def pay_participant(
        self,
        payer_user_id: uuid.UUID,
        bill_split_id: uuid.UUID,
        participant_id: uuid.UUID,
        data: BillSplitPay,
    ) -> BillSplitPublic:
        bill_split = self._get_visible(payer_user_id, bill_split_id)
        if bill_split.status != BillSplitStatus.OPEN:
            raise ConflictError(f"Bill split is {bill_split.status.value}")

        participant = self.repository.get_participant(participant_id)
        if (
            participant is None
            or participant.bill_split_id != bill_split.id
            or participant.participant_user_id != payer_user_id
        ):
            raise NotFoundError("Bill split participant not found")
        if participant.status != BillSplitParticipantStatus.PENDING:
            raise ConflictError(f"Bill split participant is {participant.status.value}")

        source = self.wallets.get_by_id(data.source_wallet_id)
        if source is None or source.user_id != payer_user_id:
            raise ValidationError("Source wallet does not belong to the paying user")
        if source.currency != bill_split.currency:
            raise ValidationError("Source wallet currency must match the bill split currency")

        destination = self.wallets.get_by_user_and_currency(bill_split.owner_user_id, bill_split.currency)
        if destination is None:
            raise NotFoundError("Bill split owner has no destination wallet in this currency")

        transaction = self.transaction_service.create_internal_transfer(
            payer_user_id,
            InternalTransferCreate(
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                amount=participant.amount,
                description=data.description or f"Bill split payment - {bill_split.title}",
            ),
            # The participant is marked PAID and the owner notified
            # "payment received" immediately below, so a fraud HOLD here
            # would announce money that hasn't arrived. Screening this flow
            # needs that status handling first — see
            # create_internal_transfer's docstring.
            screen_for_fraud=False,
        )

        participant.status = BillSplitParticipantStatus.PAID
        participant.paid_transaction_id = transaction.id
        self.db.flush()
        self._settle_if_complete(bill_split)
        self.db.flush()

        try:
            self.notifications.create(
                bill_split.owner_user_id,
                type="SPLIT_BILL",
                title="Split bill payment received",
                message=f"{participant.name} paid their {participant.amount} {bill_split.currency} share of '{bill_split.title}'.",
                related_transaction_id=transaction.id,
            )
        except Exception:
            logger.exception("Failed to notify bill-split owner %s of a received payment", bill_split.owner_user_id)
        return self._to_public(bill_split)

    def decline_participant(
        self,
        participant_user_id: uuid.UUID,
        bill_split_id: uuid.UUID,
        participant_id: uuid.UUID,
    ) -> BillSplitPublic:
        bill_split = self._get_visible(participant_user_id, bill_split_id)
        if bill_split.status != BillSplitStatus.OPEN:
            raise ConflictError(f"Bill split is {bill_split.status.value}")

        participant = self.repository.get_participant(participant_id)
        if (
            participant is None
            or participant.bill_split_id != bill_split.id
            or participant.participant_user_id != participant_user_id
        ):
            raise NotFoundError("Bill split participant not found")
        if participant.status != BillSplitParticipantStatus.PENDING:
            raise ConflictError(f"Bill split participant is {participant.status.value}")

        participant.status = BillSplitParticipantStatus.DECLINED
        self.db.flush()
        return self._to_public(bill_split)

    def _get_owned(self, owner_user_id: uuid.UUID, bill_split_id: uuid.UUID) -> BillSplit:
        bill_split = self.repository.get_owned_by_id(owner_user_id, bill_split_id)
        if bill_split is None:
            raise NotFoundError("Bill split not found")
        return bill_split

    def _get_visible(self, user_id: uuid.UUID, bill_split_id: uuid.UUID) -> BillSplit:
        bill_split = self.repository.get_visible_by_id(user_id, bill_split_id)
        if bill_split is None:
            raise NotFoundError("Bill split not found")
        return bill_split

    def _settle_if_complete(self, bill_split: BillSplit) -> None:
        participants = self.repository.list_participants(bill_split.id)
        if participants and all(participant.status == BillSplitParticipantStatus.PAID for participant in participants):
            bill_split.status = BillSplitStatus.SETTLED

    def _to_public(
        self, bill_split: BillSplit, participants: list[BillSplitParticipant] | None = None
    ) -> BillSplitPublic:
        return BillSplitPublic(
            id=bill_split.id,
            owner_user_id=bill_split.owner_user_id,
            source_transaction_id=bill_split.source_transaction_id,
            title=bill_split.title,
            total_amount=bill_split.total_amount,
            currency=bill_split.currency,
            status=bill_split.status,
            description=bill_split.description,
            created_at=bill_split.created_at,
            updated_at=bill_split.updated_at,
            participants=participants if participants is not None else self.repository.list_participants(bill_split.id),
        )


class TransactionFolderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = TransactionFolderRepository(db)
        self.transactions = TransactionRepository(db)

    def create_folder(self, owner_user_id: uuid.UUID, data: TransactionFolderCreate) -> TransactionFolderPublic:
        if self.repository.get_by_name(owner_user_id, data.name) is not None:
            raise ConflictError("Transaction folder name already exists")
        folder = self.repository.add(
            TransactionFolder(
                owner_user_id=owner_user_id,
                name=data.name,
                color=data.color,
                description=data.description,
            )
        )
        return self._to_public(folder)

    def list_folders(self, owner_user_id: uuid.UUID) -> list[TransactionFolderPublic]:
        folders = self.repository.list_for_owner(owner_user_id)
        items_by_folder = self.repository.list_items_for_folders([folder.id for folder in folders])
        return [self._to_public(folder, items_by_folder[folder.id]) for folder in folders]

    def get_folder(self, owner_user_id: uuid.UUID, folder_id: uuid.UUID) -> TransactionFolderPublic:
        return self._to_public(self._get_owned(owner_user_id, folder_id))

    def update_folder(
        self,
        owner_user_id: uuid.UUID,
        folder_id: uuid.UUID,
        data: TransactionFolderUpdate,
    ) -> TransactionFolderPublic:
        folder = self._get_owned(owner_user_id, folder_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes:
            existing = self.repository.get_by_name(owner_user_id, changes["name"])
            if existing is not None and existing.id != folder.id:
                raise ConflictError("Transaction folder name already exists")
        for field, value in changes.items():
            setattr(folder, field, value)
        self.db.flush()
        return self._to_public(folder)

    def delete_folder(self, owner_user_id: uuid.UUID, folder_id: uuid.UUID) -> None:
        folder = self._get_owned(owner_user_id, folder_id)
        self.repository.delete(folder)

    def add_transaction(
        self,
        owner_user_id: uuid.UUID,
        folder_id: uuid.UUID,
        transaction_id: uuid.UUID,
    ) -> TransactionFolderPublic:
        folder = self._get_owned(owner_user_id, folder_id)
        transaction = self.transactions.get_for_user(owner_user_id, transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found")
        if transaction.status != TransactionStatus.COMPLETED:
            raise ValidationError("Only completed transactions can be added to a folder")
        if transaction.type not in FOLDER_ELIGIBLE_TRANSACTION_TYPES:
            raise ValidationError("Only payments and cashback can be added to a folder")
        # One folder per transaction. Two folders holding the same payment
        # each count it toward their own total and can each be split
        # independently, so settling one leaves the other quietly claiming
        # money that has already been accounted for.
        existing = self.repository.get_item_for_transaction(transaction_id)
        if existing is not None:
            if existing.folder_id == folder.id:
                raise ConflictError("Transaction is already in this folder")
            raise ConflictError("Transaction is already in another folder — remove it from that one first")
        self.repository.add_item(TransactionFolderItem(folder_id=folder.id, transaction_id=transaction_id))
        return self._to_public(folder)

    def remove_transaction(self, owner_user_id: uuid.UUID, folder_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
        folder = self._get_owned(owner_user_id, folder_id)
        item = self.repository.get_item(folder.id, transaction_id)
        if item is None:
            raise NotFoundError("Transaction folder item not found")
        self.repository.delete_item(item)

    def _get_owned(self, owner_user_id: uuid.UUID, folder_id: uuid.UUID) -> TransactionFolder:
        folder = self.repository.get_owned_by_id(owner_user_id, folder_id)
        if folder is None:
            raise NotFoundError("Transaction folder not found")
        return folder

    def _to_public(
        self, folder: TransactionFolder, items: list[TransactionFolderItem] | None = None
    ) -> TransactionFolderPublic:
        return TransactionFolderPublic(
            id=folder.id,
            owner_user_id=folder.owner_user_id,
            name=folder.name,
            color=folder.color,
            description=folder.description,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            items=items if items is not None else self.repository.list_items(folder.id),
        )


class BulkTransferTemplateService:
    """Saved payroll-style batches (IbanTransferService.create_bulk_transfer)
    the owner re-runs on demand. Same "advisory record" shape as
    ScheduledPayment — nothing in this codebase runs these on a timer; the
    only thing that ever calls create_bulk_transfer here is run_now(), always
    in response to a user action, same as every other write in this
    service."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = BulkTransferTemplateRepository(db)
        self.wallets = WalletRepository(db)
        self.iban_transfers = IbanTransferService(db)

    def create_template(
        self, owner_user_id: uuid.UUID, data: BulkTransferTemplateCreate
    ) -> BulkTransferTemplate:
        wallet = self.wallets.get_by_id(data.source_wallet_id)
        if wallet is None:
            raise NotFoundError("Source wallet not found")
        if wallet.user_id != owner_user_id:
            raise ValidationError("Source wallet does not belong to the current user")
        currency = data.currency.upper()
        if wallet.currency != currency:
            raise ValidationError("Template currency must match the source wallet")

        template = self.repository.add(
            BulkTransferTemplate(
                owner_user_id=owner_user_id,
                source_wallet_id=wallet.id,
                name=data.name,
                currency=currency,
                frequency=data.frequency,
                next_run_on=data.next_run_on,
                status=ScheduledPaymentStatus.ACTIVE,
            )
        )
        for row in data.rows:
            self.repository.add_row(
                BulkTransferTemplateRow(
                    template_id=template.id,
                    beneficiary_name=row.beneficiary_name,
                    iban=row.iban,
                    amount=row.amount,
                    description=row.description,
                )
            )
        self.db.flush()
        return template

    def list_templates(self, owner_user_id: uuid.UUID) -> list[BulkTransferTemplate]:
        return self.repository.list_for_owner(owner_user_id)

    def to_public(self, template: BulkTransferTemplate) -> BulkTransferTemplatePublic:
        # Rows are fetched explicitly rather than read off template.rows —
        # the Supabase REST session doesn't populate SQLAlchemy relationships,
        # same reasoning as TransactionFolderService._to_public.
        rows = self.repository.list_rows_for_template(template.id)
        return BulkTransferTemplatePublic(
            id=template.id,
            owner_user_id=template.owner_user_id,
            source_wallet_id=template.source_wallet_id,
            name=template.name,
            currency=template.currency,
            frequency=template.frequency,
            next_run_on=template.next_run_on,
            status=template.status,
            created_at=template.created_at,
            updated_at=template.updated_at,
            rows=[
                BulkTransferTemplateRowPublic(
                    id=row.id,
                    beneficiary_name=row.beneficiary_name,
                    iban=row.iban,
                    amount=row.amount,
                    description=row.description,
                )
                for row in rows
            ],
        )

    def _get_owned_template(self, owner_user_id: uuid.UUID, template_id: uuid.UUID) -> BulkTransferTemplate:
        template = self.repository.get_owned_by_id(owner_user_id, template_id)
        if template is None:
            raise NotFoundError("Template not found")
        return template

    def update_status(
        self, owner_user_id: uuid.UUID, template_id: uuid.UUID, status: ScheduledPaymentStatus
    ) -> BulkTransferTemplate:
        template = self._get_owned_template(owner_user_id, template_id)
        allowed = _SCHEDULED_STATUS_TRANSITIONS[template.status]
        if status not in allowed:
            raise ConflictError(f"Cannot move a {template.status.value} template to {status.value}")
        template.status = status
        template.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return template

    def run_now(self, owner_user_id: uuid.UUID, template_id: uuid.UUID) -> BulkTransferResult:
        """Runs the template's rows through create_bulk_transfer right now —
        a user action, not a scheduled trigger (see class docstring) — then
        advances next_run_on, or cancels a ONCE template instead."""
        template = self._get_owned_template(owner_user_id, template_id)
        if template.status != ScheduledPaymentStatus.ACTIVE:
            raise ConflictError(f"Template is {template.status.value}, not ACTIVE")

        rows = self.repository.list_rows_for_template(template.id)
        result = self.iban_transfers.create_bulk_transfer(
            owner_user_id,
            BulkTransferCreate(
                source_wallet_id=template.source_wallet_id,
                currency=template.currency,
                rows=[
                    BulkTransferRow(
                        beneficiary_name=row.beneficiary_name,
                        iban=row.iban,
                        amount=row.amount,
                        description=row.description,
                    )
                    for row in rows
                ],
            ),
        )

        if template.frequency == ScheduledPaymentFrequency.ONCE:
            template.status = ScheduledPaymentStatus.CANCELLED
        else:
            template.next_run_on = _advance_by_frequency(template.next_run_on, template.frequency)
        template.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return result
