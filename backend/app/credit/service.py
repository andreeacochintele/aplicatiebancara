"""Credit profile and score business rules."""
import base64
import binascii
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.cards.models import CardStatus, CardTier, CardType, CreditCardAccount
from app.cards.repository import CardRepository
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.database import utcnow
from app.credit.loan_calculator import calculate_loan_schedule
from app.credit.models import (
    CreditApplication,
    CreditApplicationStatus,
    CreditApplicationType,
    CreditDocument,
    CreditDocumentPurpose,
    CreditDocumentStatus,
    CreditProfile,
    CreditScoreHistory,
    Loan,
    LoanInstallment,
    LoanInstallmentStatus,
    LoanPayment,
    LoanPaymentType,
    LoanProductType,
    LoanStatus,
)
from app.credit.products import get_loan_product, list_loan_products
from app.credit.repository import CreditRepository
from app.credit.schemas import (
    CreditApplicationCreate,
    CreditApplicationDecision,
    CreditApplicationDocumentCreate,
    CreditApplicationPublic,
    CreditDocumentCreate,
    CreditDocumentPublic,
    CreditDocumentContentPublic,
    CreditDocumentReview,
    EarlyRepaymentPaymentResult,
    EarlyRepaymentResult,
    LoanProductPublic,
    CreditScorePublic,
    CreditScoreRecalculateRequest,
    LoanCalculatorRequest,
    LoanCalculatorResult,
    RegularInstallmentPaymentResult,
)
from app.credit.scoring import calculate_credit_score, credit_band
from app.notifications.service import NotificationsService
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.supabase import is_supabase_session
from app.wallets.models import Wallet, WalletStatus
from app.wallets.repository import WalletRepository
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


class CreditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CreditRepository(db)
        self.wallets = WalletRepository(db)
        self.cards = CardRepository(db)
        self.transactions = TransactionRepository(db)
        self.notifications = NotificationsService(db)

    def get_or_create_profile(self, user_id: uuid.UUID) -> CreditProfile:
        profile = self.repository.get_profile_by_user(user_id)
        if profile is not None:
            return profile

        profile = self.repository.add_profile(CreditProfile(user_id=user_id))
        self._persist_score(profile, self._wallet_balance(user_id))
        return profile

    def get_score(self, user_id: uuid.UUID) -> CreditScorePublic:
        profile = self.get_or_create_profile(user_id)
        latest = self.repository.latest_history(profile.id)
        if latest is None:
            latest = self._persist_score(profile, self._wallet_balance(user_id))
        return CreditScorePublic(
            score=profile.current_score,
            band=credit_band(profile.current_score),
            reason_data=latest.reason_data,
            calculated_at=latest.created_at,
        )

    def recalculate_score(self, user_id: uuid.UUID, data: CreditScoreRecalculateRequest) -> CreditScorePublic:
        profile = self.repository.get_profile_by_user(user_id)
        if profile is None:
            profile = self.repository.add_profile(CreditProfile(user_id=user_id))

        if data.income is not None:
            profile.income = data.income
        if data.currency is not None:
            profile.currency = _normalize_currency(data.currency)

        loan_debt = self._loan_debt(user_id)
        profile.existing_debt = loan_debt
        score, factors = calculate_credit_score(profile.income, profile.existing_debt, self._wallet_balance(user_id))
        return CreditScorePublic(
            score=score,
            band=credit_band(score),
            reason_data={
                **factors,
                "wallet_balance": str(self._wallet_balance(user_id)),
                "income": str(profile.income),
                "existing_debt": str(profile.existing_debt),
                "profile_currency": profile.currency,
                "review_status": "PENDING_ADMIN_REVIEW",
            },
            calculated_at=utcnow(),
        )

    def create_application(self, user_id: uuid.UUID, data: CreditApplicationCreate) -> CreditApplication:
        if data.requested_amount <= 0:
            raise ValidationError("Requested amount must be positive")
        currency = _normalize_currency(data.currency)
        loan_documents: list[CreditDocument] = []
        if data.type == CreditApplicationType.PERSONAL_LOAN:
            loan_product_type = data.loan_product_type or LoanProductType.PERSONAL_LOAN
            if data.requested_term_months is None or data.requested_term_months <= 0:
                raise ValidationError("Loan applications require a positive term")
            get_loan_product(loan_product_type)
            if data.documents is not None and len(data.documents) == 0:
                raise ValidationError("Loan applications require supporting documents")
            loan_documents = [
                self._prepare_document_upload(
                    user_id=user_id,
                    data=document,
                    purpose=CreditDocumentPurpose.LOAN_APPLICATION,
                    application_id=None,
                )
                for document in data.documents or []
            ]
            if loan_documents:
                self._ensure_document_storage_or_raise_setup_error()
            status = CreditApplicationStatus.PENDING
            offered_amount = None
            offered_interest_rate = None
            resolved_at = None
        else:
            loan_product_type = None
            status = CreditApplicationStatus.PENDING
            offered_amount = None
            offered_interest_rate = None
            resolved_at = None
            if data.requested_term_months is not None and data.requested_term_months <= 0:
                raise ValidationError("Requested term must be positive")

        score = self.get_score(user_id)
        application = CreditApplication(
            user_id=user_id,
            type=data.type,
            loan_product_type=loan_product_type,
            requested_amount=data.requested_amount,
            currency=currency,
            requested_term_months=data.requested_term_months,
            offered_amount=offered_amount,
            offered_interest_rate=offered_interest_rate,
            credit_score_at_application=score.score,
            status=status,
            resolved_at=resolved_at,
        )
        application = self.repository.add_application(application)
        created_documents: list[CreditDocument] = []
        for document in loan_documents:
            document.application_id = application.id
            created_documents.append(self._add_document_or_raise_setup_error(document))
        if created_documents:
            application.documents = created_documents
        return application

    def calculate_loan(self, data: LoanCalculatorRequest) -> LoanCalculatorResult:
        return calculate_loan_schedule(data)

    def list_loan_products(self) -> list[LoanProductPublic]:
        return list_loan_products()

    def create_loan_from_application(self, user_id: uuid.UUID, application_id: uuid.UUID) -> Loan:
        application = self.get_application_for_user(user_id, application_id)
        if application.type != CreditApplicationType.PERSONAL_LOAN:
            raise ValidationError("Only loan applications can create loans")
        if application.status != CreditApplicationStatus.APPROVED:
            raise ValidationError("Only approved applications can create loans")
        if application.requested_term_months is None or application.requested_term_months <= 0:
            raise ValidationError("Approved loan applications require a positive term")
        if application.offered_amount is None or application.offered_amount <= 0:
            raise ValidationError("Approved loan applications require a positive offered amount")
        if application.offered_interest_rate is None or application.offered_interest_rate < 0:
            raise ValidationError("Approved loan applications require a non-negative offered interest rate")
        existing_loan = self.repository.get_loan_by_application(application.id)
        if existing_loan is not None:
            return existing_loan
        disbursement_wallet = self._get_or_create_disbursement_wallet(user_id, application.currency)

        start_date = utcnow().date()
        maturity_date = _add_months(start_date, application.requested_term_months)
        next_payment_date = _add_months(start_date, 1)
        preview = calculate_loan_schedule(
            LoanCalculatorRequest(
                principal_amount=application.offered_amount,
                currency=application.currency,
                annual_interest_rate=application.offered_interest_rate,
                term_months=application.requested_term_months,
            )
        )
        loan = self.repository.add_loan(
            Loan(
                user_id=user_id,
                application_id=application.id,
                principal_amount=preview.principal_amount,
                currency=preview.currency,
                interest_rate=preview.annual_interest_rate,
                term_months=preview.term_months,
                monthly_payment=preview.monthly_payment,
                outstanding_principal=preview.principal_amount,
                start_date=start_date,
                maturity_date=maturity_date,
                next_payment_date=next_payment_date,
            )
        )
        self.repository.add_installments(
            [
                LoanInstallment(
                    loan_id=loan.id,
                    installment_number=item.installment_number,
                    due_date=_add_months(start_date, item.installment_number),
                    payment_amount=item.payment_amount,
                    principal_amount=item.principal_amount,
                    interest_amount=item.interest_amount,
                    fees_amount=Decimal("0.00"),
                    remaining_principal=item.remaining_principal,
                )
                for item in preview.schedule
            ]
        )
        self._disburse_loan(application, loan, disbursement_wallet)
        return loan

    def list_loans(self, user_id: uuid.UUID) -> list[Loan]:
        return self.repository.list_loans_for_user(user_id)

    def get_loan_for_user(self, user_id: uuid.UUID, loan_id: uuid.UUID) -> Loan:
        loan = self.repository.get_loan_by_id(loan_id)
        if loan is None or loan.user_id != user_id:
            raise NotFoundError("Loan not found")
        return loan

    def list_installments_for_loan(self, user_id: uuid.UUID, loan_id: uuid.UUID) -> list[LoanInstallment]:
        loan = self.get_loan_for_user(user_id, loan_id)
        return self.repository.list_installments_for_loan(loan.id)

    def simulate_early_repayment(
        self,
        user_id: uuid.UUID,
        loan_id: uuid.UUID,
        extra_payment_amount: Decimal,
    ) -> EarlyRepaymentResult:
        if extra_payment_amount <= 0:
            raise ValidationError("Extra payment amount must be positive")

        loan = self.get_loan_for_user(user_id, loan_id)
        if loan.status != LoanStatus.ACTIVE:
            raise ValidationError("Only active loans can be simulated")

        installments = self.repository.list_installments_for_loan(loan.id)
        pending_installments = [
            installment for installment in installments if installment.status == LoanInstallmentStatus.PENDING
        ]
        remaining_term_months = len(pending_installments) or loan.term_months
        total_interest_before = _money(
            sum((installment.interest_amount for installment in pending_installments), Decimal("0.00"))
        )
        if not pending_installments:
            total_interest_before = _remaining_interest_for_fixed_payment(
                loan.outstanding_principal,
                loan.interest_rate,
                loan.monthly_payment,
            )

        original_outstanding = _money(loan.outstanding_principal)
        applied_extra_payment = min(_money(extra_payment_amount), original_outstanding)
        new_outstanding = _money(original_outstanding - applied_extra_payment)
        revised_term_months, total_interest_after = _simulate_fixed_payment_payoff(
            new_outstanding,
            loan.interest_rate,
            loan.monthly_payment,
        )

        term_months_reduced = max(0, remaining_term_months - revised_term_months)
        total_interest_saved = max(Decimal("0.00"), _money(total_interest_before - total_interest_after))

        return EarlyRepaymentResult(
            loan_id=loan.id,
            currency=loan.currency,
            original_outstanding_principal=original_outstanding,
            extra_payment_amount=_money(extra_payment_amount),
            applied_extra_payment_amount=applied_extra_payment,
            new_outstanding_principal=new_outstanding,
            remaining_term_months=remaining_term_months,
            revised_term_months=revised_term_months,
            term_months_reduced=term_months_reduced,
            total_interest_before=total_interest_before,
            total_interest_after=total_interest_after,
            total_interest_saved=total_interest_saved,
        )

    def make_early_repayment(
        self,
        user_id: uuid.UUID,
        loan_id: uuid.UUID,
        source_wallet_id: uuid.UUID | None,
        amount: Decimal,
        source_card_id: uuid.UUID | None = None,
    ) -> EarlyRepaymentPaymentResult:
        simulation = self.simulate_early_repayment(user_id, loan_id, amount)
        loan = self.get_loan_for_user(user_id, loan_id)
        source_card = None
        if source_card_id is not None:
            source_card = self.cards.get_by_id(source_card_id)
            if source_card is None or source_card.user_id != user_id:
                raise NotFoundError("Source card not found")
            if source_card.status != CardStatus.ACTIVE:
                raise ValidationError("Source card must be active")

        wallet = self.wallets.get_by_id(source_wallet_id) if source_wallet_id is not None else None
        if source_card is None or source_card.type != CardType.CREDIT:
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Source wallet not found")
            if wallet.currency != loan.currency:
                raise ValidationError("Payment source currency must match the loan currency")
            if wallet.available_balance < simulation.applied_extra_payment_amount:
                raise ConflictError("Insufficient available balance")
            if source_card is not None:
                if source_card.type != CardType.DEBIT:
                    raise ValidationError("Only debit or credit cards can be used as a loan payment card source")
                if source_card.default_wallet_id != wallet.id:
                    raise ValidationError("Source debit card must be linked to the selected wallet")
        else:
            account = CardService(self.db)._get_or_create_credit_account(source_card)
            if account.currency != loan.currency:
                raise ValidationError("Credit card currency must match the loan currency")
            if account.available_credit < simulation.applied_extra_payment_amount:
                raise ConflictError("Insufficient available credit")

        paid_at = utcnow()
        transaction = self.transactions.add(
            Transaction(
                initiator_user_id=user_id,
                source_wallet_id=wallet.id if wallet is not None else None,
                card_id=source_card.id if source_card is not None else None,
                type=TransactionType.LOAN_PAYMENT,
                status=TransactionStatus.PROCESSING,
                amount=simulation.applied_extra_payment_amount,
                currency=loan.currency,
                description=(
                    f"Loan payment with credit card ending {source_card.last_four}"
                    if source_card is not None and source_card.type == CardType.CREDIT
                    else f"Early repayment for loan {loan.id}"
                ),
                processed_at=paid_at,
            )
        )

        if wallet is not None:
            wallet.available_balance = _money(wallet.available_balance - simulation.applied_extra_payment_amount)
            self.transactions.add_ledger_entry(
                WalletLedgerEntry(
                    wallet_id=wallet.id,
                    transaction_id=transaction.id,
                    entry_type=LedgerEntryType.DEBIT,
                    amount=simulation.applied_extra_payment_amount,
                    currency=wallet.currency,
                    balance_after=wallet.available_balance,
                )
            )
        elif source_card is not None:
            account.used_amount = _money(account.used_amount + simulation.applied_extra_payment_amount)
            account.updated_at = paid_at

        loan.outstanding_principal = simulation.new_outstanding_principal
        if loan.outstanding_principal == Decimal("0.00"):
            loan.status = LoanStatus.CLOSED if is_supabase_session(self.db) else LoanStatus.PAID
            loan.closed_at = paid_at
        self._reschedule_pending_installments_after_early_repayment(loan)

        self.repository.add_loan_payment(
            LoanPayment(
                loan_id=loan.id,
                transaction_id=transaction.id,
                amount=simulation.applied_extra_payment_amount,
                principal_paid=simulation.applied_extra_payment_amount,
                interest_paid=Decimal("0.00"),
                payment_type=LoanPaymentType.EARLY_REPAYMENT,
            )
        )

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = paid_at
        self.db.flush()

        return EarlyRepaymentPaymentResult(
            **simulation.model_dump(),
            transaction_id=transaction.id,
            loan_status=loan.status,
        )

    def make_regular_installment_payment(
        self,
        user_id: uuid.UUID,
        loan_id: uuid.UUID,
        source_wallet_id: uuid.UUID | None,
        source_card_id: uuid.UUID | None = None,
    ) -> RegularInstallmentPaymentResult:
        loan = self.get_loan_for_user(user_id, loan_id)
        if loan.status != LoanStatus.ACTIVE:
            raise ValidationError("Only active loans can receive installment payments")

        pending_installments = [
            installment
            for installment in self.repository.list_installments_for_loan(loan.id)
            if installment.status == LoanInstallmentStatus.PENDING
        ]
        if not pending_installments:
            raise ValidationError("This loan has no pending installments")
        installment = pending_installments[0]
        amount = _money(installment.payment_amount)
        source_card, wallet, account = self._validate_loan_payment_source(
            user_id,
            loan,
            amount,
            source_wallet_id,
            source_card_id,
        )

        paid_at = utcnow()
        transaction = self.transactions.add(
            Transaction(
                initiator_user_id=user_id,
                source_wallet_id=wallet.id if wallet is not None else None,
                card_id=source_card.id if source_card is not None else None,
                type=TransactionType.LOAN_PAYMENT,
                status=TransactionStatus.PROCESSING,
                amount=amount,
                currency=loan.currency,
                description=f"Regular installment for loan {loan.id}",
                processed_at=paid_at,
            )
        )

        if wallet is not None:
            wallet.available_balance = _money(wallet.available_balance - amount)
            self.transactions.add_ledger_entry(
                WalletLedgerEntry(
                    wallet_id=wallet.id,
                    transaction_id=transaction.id,
                    entry_type=LedgerEntryType.DEBIT,
                    amount=amount,
                    currency=wallet.currency,
                    balance_after=wallet.available_balance,
                )
            )
        elif account is not None:
            account.used_amount = _money(account.used_amount + amount)
            account.updated_at = paid_at

        installment.status = LoanInstallmentStatus.PAID
        loan.outstanding_principal = _money(installment.remaining_principal)
        next_installment = next(
            (item for item in pending_installments[1:] if item.status == LoanInstallmentStatus.PENDING),
            None,
        )
        if next_installment is None or loan.outstanding_principal == Decimal("0.00"):
            loan.outstanding_principal = Decimal("0.00")
            loan.status = LoanStatus.CLOSED if is_supabase_session(self.db) else LoanStatus.PAID
            loan.closed_at = paid_at
            next_payment_date = None
        else:
            loan.next_payment_date = next_installment.due_date
            next_payment_date = loan.next_payment_date

        self.repository.add_loan_payment(
            LoanPayment(
                loan_id=loan.id,
                transaction_id=transaction.id,
                amount=amount,
                principal_paid=installment.principal_amount,
                interest_paid=installment.interest_amount,
                fees_paid=installment.fees_amount,
                payment_type=LoanPaymentType.REGULAR,
            )
        )

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = paid_at
        self.db.flush()

        return RegularInstallmentPaymentResult(
            loan_id=loan.id,
            installment_id=installment.id,
            transaction_id=transaction.id,
            amount=amount,
            principal_paid=installment.principal_amount,
            interest_paid=installment.interest_amount,
            fees_paid=installment.fees_amount,
            remaining_principal=loan.outstanding_principal,
            next_payment_date=next_payment_date,
            loan_status=loan.status,
        )

    def _validate_loan_payment_source(
        self,
        user_id: uuid.UUID,
        loan: Loan,
        amount: Decimal,
        source_wallet_id: uuid.UUID | None,
        source_card_id: uuid.UUID | None,
    ) -> tuple[object | None, Wallet | None, CreditCardAccount | None]:
        source_card = None
        if source_card_id is not None:
            source_card = self.cards.get_by_id(source_card_id)
            if source_card is None or source_card.user_id != user_id:
                raise NotFoundError("Source card not found")
            if source_card.status != CardStatus.ACTIVE:
                raise ValidationError("Source card must be active")

        wallet = self.wallets.get_by_id(source_wallet_id) if source_wallet_id is not None else None
        account = None
        if source_card is None or source_card.type != CardType.CREDIT:
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Source wallet not found")
            if wallet.currency != loan.currency:
                raise ValidationError("Payment source currency must match the loan currency")
            if wallet.available_balance < amount:
                raise ConflictError("Insufficient available balance")
            if source_card is not None:
                if source_card.type != CardType.DEBIT:
                    raise ValidationError("Only debit or credit cards can be used as a loan payment card source")
                if source_card.default_wallet_id != wallet.id:
                    raise ValidationError("Source debit card must be linked to the selected wallet")
        else:
            account = CardService(self.db)._get_or_create_credit_account(source_card)
            if account.currency != loan.currency:
                raise ValidationError("Credit card currency must match the loan currency")
            if account.available_credit < amount:
                raise ConflictError("Insufficient available credit")
        return source_card, wallet, account

    def _reschedule_pending_installments_after_early_repayment(self, loan: Loan) -> None:
        installments = self.repository.list_installments_for_loan(loan.id)
        pending_installments = [
            installment for installment in installments if installment.status == LoanInstallmentStatus.PENDING
        ]
        if not pending_installments:
            return
        if loan.outstanding_principal == Decimal("0.00"):
            self.repository.delete_installments(pending_installments)
            return

        revised_schedule = _fixed_payment_payoff_schedule(
            loan.outstanding_principal,
            loan.interest_rate,
            loan.monthly_payment,
        )
        for installment, item in zip(pending_installments, revised_schedule):
            payment_amount, principal_amount, interest_amount, remaining_principal = item
            installment.payment_amount = payment_amount
            installment.principal_amount = principal_amount
            installment.interest_amount = interest_amount
            installment.fees_amount = Decimal("0.00")
            installment.remaining_principal = remaining_principal
            installment.status = LoanInstallmentStatus.PENDING

        self.repository.delete_installments(pending_installments[len(revised_schedule):])
        if revised_schedule:
            loan.maturity_date = pending_installments[len(revised_schedule) - 1].due_date

    def list_applications(self, user_id: uuid.UUID) -> list[CreditApplication]:
        return self.repository.list_applications_for_user(user_id)

    def list_all_applications(self) -> list[CreditApplication]:
        return self.repository.list_applications()

    def list_all_applications_with_documents(self) -> list[CreditApplicationPublic]:
        applications = self.repository.list_applications()
        documents = self.repository.list_documents()
        grouped_documents = self._group_documents_by_application(applications, documents)
        return [self._application_public(application, grouped_documents.get(application.id, [])) for application in applications]

    def get_application_public(self, application_id: uuid.UUID) -> CreditApplicationPublic:
        application = self.repository.get_application_by_id(application_id)
        if application is None:
            raise NotFoundError("Credit application not found")
        documents = self.repository.list_documents()
        grouped_documents = self._group_documents_by_application([application], documents)
        return self._application_public(application, grouped_documents.get(application.id, []))

    def upload_document(self, user_id: uuid.UUID, data: CreditDocumentCreate) -> CreditDocument:
        application_id = data.application_id
        if application_id is not None:
            application = self.repository.get_application_by_id(application_id)
            if application is None or application.user_id != user_id:
                raise NotFoundError("Credit application not found")
        if data.purpose == CreditDocumentPurpose.LOAN_APPLICATION and application_id is None:
            raise ValidationError("Loan application documents must be linked to an application")

        document = self._prepare_document_upload(
            user_id=user_id,
            data=data,
            purpose=data.purpose,
            application_id=application_id,
        )
        if data.purpose == CreditDocumentPurpose.CREDIT_SCORE:
            profile = self._get_or_create_profile_record(user_id)
            profile.existing_debt = self._loan_debt(user_id)
            generated_score, _factors = calculate_credit_score(
                profile.income,
                profile.existing_debt,
                self._wallet_balance(user_id),
            )
            document.evaluation_score = generated_score
        return self._add_document_or_raise_setup_error(document)

    def _add_document_or_raise_setup_error(self, document: CreditDocument) -> CreditDocument:
        try:
            return self.repository.add_document(document)
        except RuntimeError as exc:
            if "Credit document storage is not configured in Supabase" in str(exc):
                raise ValidationError(str(exc)) from exc
            raise

    def _ensure_document_storage_or_raise_setup_error(self) -> None:
        try:
            self.repository.ensure_document_storage_available()
        except RuntimeError as exc:
            if "Credit document storage is not configured in Supabase" in str(exc):
                raise ValidationError(str(exc)) from exc
            raise

    def _prepare_document_upload(
        self,
        user_id: uuid.UUID,
        data: CreditDocumentCreate | CreditApplicationDocumentCreate,
        purpose: CreditDocumentPurpose,
        application_id: uuid.UUID | None,
    ) -> CreditDocument:
        if data.file_size < 0:
            raise ValidationError("Document file size cannot be negative")
        if not data.file_name.strip():
            raise ValidationError("Document file name is required")
        if not data.document_type.strip():
            raise ValidationError("Document type is required")
        content_base64 = data.content_base64.strip() if data.content_base64 else None
        if content_base64 is not None:
            try:
                decoded_size = len(base64.b64decode(content_base64, validate=True))
            except (binascii.Error, ValueError) as exc:
                raise ValidationError("Document content must be valid base64") from exc
            if decoded_size != data.file_size:
                raise ValidationError("Document file size does not match uploaded content")

        return CreditDocument(
            user_id=user_id,
            application_id=application_id,
            purpose=purpose,
            document_type=data.document_type.strip(),
            file_name=data.file_name.strip(),
            content_type=data.content_type,
            file_size=data.file_size,
            content_base64=content_base64,
            status=CreditDocumentStatus.UPLOADED,
            uploaded_at=utcnow(),
        )

    def list_documents(self, user_id: uuid.UUID) -> list[CreditDocument]:
        return self.repository.list_documents_for_user(user_id)

    def list_all_documents(self) -> list[CreditDocument]:
        return self.repository.list_documents()

    def get_document_content_for_user(self, user_id: uuid.UUID, document_id: uuid.UUID) -> CreditDocumentContentPublic:
        document = self.repository.get_document_by_id(document_id)
        if document is None or document.user_id != user_id:
            raise NotFoundError("Credit document not found")
        return self._document_content_response(document)

    def get_document_content_for_admin(self, document_id: uuid.UUID) -> CreditDocumentContentPublic:
        document = self.repository.get_document_by_id(document_id)
        if document is None:
            raise NotFoundError("Credit document not found")
        return self._document_content_response(document)

    def review_document(
        self,
        document_id: uuid.UUID,
        admin_id: uuid.UUID,
        data: CreditDocumentReview,
    ) -> CreditDocument:
        document = self.repository.get_document_by_id(document_id)
        if document is None:
            raise NotFoundError("Credit document not found")
        if data.status == CreditDocumentStatus.UPLOADED:
            raise ValidationError("Document review must approve, reject or request more information")
        max_evaluation_score = 850 if document.purpose == CreditDocumentPurpose.CREDIT_SCORE else 100
        if data.evaluation_score is not None and not 0 <= data.evaluation_score <= max_evaluation_score:
            raise ValidationError(f"Document evaluation score must be between 0 and {max_evaluation_score}")

        document.status = data.status
        document.evaluation_score = data.evaluation_score
        document.review_note = data.review_note.strip() if data.review_note else None
        document.reviewed_by_admin_id = admin_id
        document.reviewed_at = utcnow()
        if document.purpose == CreditDocumentPurpose.CREDIT_SCORE and data.status == CreditDocumentStatus.APPROVED:
            profile = self._get_or_create_profile_record(document.user_id)
            profile.existing_debt = self._loan_debt(document.user_id)
            if document.evaluation_score is None:
                document.evaluation_score, _factors = calculate_credit_score(
                    profile.income,
                    profile.existing_debt,
                    self._wallet_balance(document.user_id),
                )
            self._persist_score(profile, self._wallet_balance(document.user_id), score_override=document.evaluation_score)
        self.repository.persist_document(document)
        self.db.flush()
        return document

    def _document_content_response(self, document: CreditDocument) -> CreditDocumentContentPublic:
        if not document.content_base64:
            raise NotFoundError("Uploaded document content is not available")
        return CreditDocumentContentPublic(
            id=document.id,
            file_name=document.file_name,
            content_type=document.content_type,
            content_base64=document.content_base64,
        )

    def get_application_for_user(self, user_id: uuid.UUID, application_id: uuid.UUID) -> CreditApplication:
        application = self.repository.get_application_by_id(application_id)
        if application is None or application.user_id != user_id:
            raise NotFoundError("Credit application not found")
        return application

    def decide_application(
        self,
        application_id: uuid.UUID,
        data: CreditApplicationDecision,
        admin_id: uuid.UUID | None = None,
    ) -> CreditApplication:
        application = self.repository.get_application_by_id(application_id)
        if application is None:
            raise NotFoundError("Credit application not found")
        if application.status != CreditApplicationStatus.PENDING:
            raise ValidationError("Only pending applications can be decided")
        if data.status not in {CreditApplicationStatus.APPROVED, CreditApplicationStatus.REJECTED}:
            raise ValidationError("Credit applications can only be approved or rejected")

        if data.status == CreditApplicationStatus.APPROVED:
            if application.type == CreditApplicationType.PERSONAL_LOAN:
                if application.loan_product_type is None:
                    raise ValidationError("Loan applications require a product type")
                rejected_documents = [
                    document
                    for document in self._loan_application_documents(application)
                    if document.status == CreditDocumentStatus.REJECTED
                ]
                if rejected_documents:
                    raise ValidationError("Cannot approve a loan application with rejected supporting documents")
                loan_product = get_loan_product(application.loan_product_type)
                application.offered_amount = application.requested_amount
                application.offered_interest_rate = loan_product.representative_apr
            else:
                if data.offered_amount is None or data.offered_amount <= 0:
                    raise ValidationError("Approved applications require a positive offered amount")
                if data.offered_interest_rate is None or data.offered_interest_rate < 0:
                    raise ValidationError("Approved applications require a non-negative offered interest rate")
                application.offered_amount = data.offered_amount
                application.offered_interest_rate = data.offered_interest_rate
        else:
            application.offered_amount = None
            application.offered_interest_rate = None

        application.status = data.status
        application.resolved_at = utcnow()
        self._mark_application_documents_reviewed(application, data.status, admin_id)
        self.db.flush()

        if application.status == CreditApplicationStatus.APPROVED:
            if application.type == CreditApplicationType.PERSONAL_LOAN:
                self.create_loan_from_application(application.user_id, application.id)
            elif application.type == CreditApplicationType.CREDIT_CARD:
                self._create_credit_card_from_approved_application(application)

        try:
            if data.status == CreditApplicationStatus.APPROVED:
                product_name = (
                    get_loan_product(application.loan_product_type).name.lower()
                    if application.loan_product_type is not None
                    else "credit"
                )
                self.notifications.create(
                    application.user_id,
                    type="CREDIT",
                    title="Credit application approved",
                    message=f"Your {product_name} application for {application.offered_amount} {application.currency} was approved "
                    f"at {application.offered_interest_rate}% APR.",
                )
            else:
                self.notifications.create(
                    application.user_id,
                    type="CREDIT",
                    title="Credit application rejected",
                    message=f"Your application for {application.requested_amount} {application.currency} was rejected.",
                )
        except Exception:
            pass
        return application

    def _create_credit_card_from_approved_application(self, application: CreditApplication) -> None:
        offered_amount = application.offered_amount or application.requested_amount
        offered_interest_rate = application.offered_interest_rate or Decimal("18.00")
        existing_cards = [
            card
            for card in self.cards.list_for_user(application.user_id)
            if card.type == CardType.CREDIT
            and card.credit_account is not None
            and card.credit_account.credit_limit == offered_amount
            and card.credit_account.currency == application.currency
            and card.created_at >= application.created_at
        ]
        if existing_cards:
            return
        CardService(self.db).create_card(
            application.user_id,
            CardCreate(type=CardType.CREDIT, tier=self._tier_for_credit_limit(offered_amount)),
            admin_approved=True,
            credit_limit=offered_amount,
            annual_interest_rate=offered_interest_rate,
            currency=application.currency,
        )

    def _tier_for_credit_limit(self, amount: Decimal) -> CardTier:
        if amount >= Decimal("30000.00"):
            return CardTier.PLATINUM
        if amount >= Decimal("15000.00"):
            return CardTier.GOLD
        return CardTier.REGULAR

    def request_application_more_info(self, application_id: uuid.UUID, admin_id: uuid.UUID | None = None) -> CreditApplication:
        application = self.repository.get_application_by_id(application_id)
        if application is None:
            raise NotFoundError("Credit application not found")
        if application.status != CreditApplicationStatus.PENDING:
            raise ValidationError("Only pending applications can request more information")

        documents = [
            document
            for document in self.repository.list_documents()
            if document.purpose == CreditDocumentPurpose.LOAN_APPLICATION and document.application_id == application.id
        ]
        if not documents:
            raise ValidationError("This loan application has no documents to request more information on")

        review_time = utcnow()
        for document in documents:
            if document.status in {CreditDocumentStatus.APPROVED, CreditDocumentStatus.REJECTED}:
                continue
            document.status = CreditDocumentStatus.NEEDS_MORE_INFO
            document.evaluation_score = None
            document.review_note = "Additional supporting information required."
            document.reviewed_by_admin_id = admin_id
            document.reviewed_at = review_time
            self.repository.persist_document(document)

        try:
            product_name = (
                get_loan_product(application.loan_product_type).name.lower()
                if application.loan_product_type is not None
                else "loan"
            )
            self.notifications.create(
                application.user_id,
                type="CREDIT",
                title="More loan information required",
                message=f"We need more documents for your {product_name} application for "
                f"{application.requested_amount} {application.currency}. Open Credit to upload the requested information.",
            )
        except Exception:
            pass
        self.db.flush()
        return application

    def _mark_application_documents_reviewed(
        self,
        application: CreditApplication,
        status: CreditApplicationStatus,
        admin_id: uuid.UUID | None,
    ) -> None:
        document_status = (
            CreditDocumentStatus.APPROVED if status == CreditApplicationStatus.APPROVED else CreditDocumentStatus.REJECTED
        )
        review_note = (
            "Document accepted with loan approval."
            if status == CreditApplicationStatus.APPROVED
            else "Document rejected with loan application."
        )
        documents = self._loan_application_documents(application)
        for document in documents:
            if document.status in {CreditDocumentStatus.APPROVED, CreditDocumentStatus.REJECTED}:
                continue
            document.status = document_status
            document.review_note = review_note
            document.reviewed_by_admin_id = admin_id
            document.reviewed_at = utcnow()
            self.repository.persist_document(document)

    def _loan_application_documents(self, application: CreditApplication) -> list[CreditDocument]:
        return [
            document
            for document in self.repository.list_documents()
            if document.purpose == CreditDocumentPurpose.LOAN_APPLICATION and document.application_id == application.id
        ]

    def _wallet_balance(self, user_id: uuid.UUID) -> Decimal:
        return sum((wallet.available_balance for wallet in self.wallets.list_for_user(user_id)), Decimal("0"))

    def _loan_debt(self, user_id: uuid.UUID) -> Decimal:
        return _money(
            sum(
                (
                    loan.outstanding_principal
                    for loan in self.repository.list_loans_for_user(user_id)
                    if loan.status == LoanStatus.ACTIVE
                ),
                Decimal("0.00"),
            )
        )

    def _get_or_create_profile_record(self, user_id: uuid.UUID) -> CreditProfile:
        profile = self.repository.get_profile_by_user(user_id)
        if profile is not None:
            return profile
        return self.repository.add_profile(CreditProfile(user_id=user_id))

    def _persist_score(
        self,
        profile: CreditProfile,
        wallet_balance: Decimal,
        score_override: int | None = None,
    ) -> CreditScoreHistory:
        profile.existing_debt = self._loan_debt(profile.user_id)
        score, factors = calculate_credit_score(profile.income, profile.existing_debt, wallet_balance)
        if score_override is not None:
            score = score_override
        profile.current_score = score
        history = CreditScoreHistory(
            credit_profile_id=profile.id,
            score=score,
            reason_data={
                **factors,
                "wallet_balance": str(wallet_balance),
                "income": str(profile.income),
                "existing_debt": str(profile.existing_debt),
                "profile_currency": profile.currency,
            },
        )
        return self.repository.add_history(history)

    def _disburse_loan(self, application: CreditApplication, loan: Loan, wallet: Wallet) -> None:
        disbursed_at = utcnow()
        amount = _money(application.offered_amount or loan.principal_amount)
        product_name = get_loan_product(application.loan_product_type).name if application.loan_product_type else "Loan"
        transaction = self.transactions.add(
            Transaction(
                initiator_user_id=application.user_id,
                destination_wallet_id=wallet.id,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=application.currency,
                description=f"{product_name} disbursement",
                processed_at=disbursed_at,
                completed_at=disbursed_at,
            )
        )
        wallet.available_balance = _money(wallet.available_balance + amount)
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )
        self.db.flush()

    def _ensure_disbursement_history(self, user_id: uuid.UUID, loans: list[Loan]) -> None:
        for loan in loans:
            if loan.status != LoanStatus.ACTIVE:
                continue
            application = loan.application or self.repository.get_application_by_id(loan.application_id)
            if application is None:
                continue
            wallet = self.wallets.get_by_user_and_currency(user_id, loan.currency)
            if wallet is None:
                continue
            amount = _money(application.offered_amount or loan.principal_amount)
            product_name = get_loan_product(application.loan_product_type).name if application.loan_product_type else "Loan"
            description = f"{product_name} disbursement"
            existing = [
                transaction
                for transaction in self.transactions.list_for_user(user_id)
                if transaction.destination_wallet_id == wallet.id
                and transaction.amount == amount
                and transaction.currency == loan.currency
                and transaction.description == description
                and transaction.status == TransactionStatus.COMPLETED
            ]
            if existing:
                continue
            transaction = self.transactions.add(
                Transaction(
                    initiator_user_id=user_id,
                    destination_wallet_id=wallet.id,
                    type=TransactionType.TRANSFER,
                    status=TransactionStatus.COMPLETED,
                    amount=amount,
                    currency=loan.currency,
                    description=description,
                    processed_at=loan.created_at,
                    completed_at=loan.created_at,
                )
            )
            self.transactions.add_ledger_entry(
                WalletLedgerEntry(
                    wallet_id=wallet.id,
                    transaction_id=transaction.id,
                    entry_type=LedgerEntryType.CREDIT,
                    amount=amount,
                    currency=wallet.currency,
                    balance_after=wallet.available_balance,
                )
            )
        self.db.flush()

    def _get_or_create_disbursement_wallet(self, user_id: uuid.UUID, currency: str) -> Wallet:
        wallet = self.wallets.get_by_user_and_currency(user_id, currency)
        if wallet is None or wallet.status == WalletStatus.CLOSED:
            return WalletService(self.db).create_wallet(user_id, WalletCreate(currency=currency))
        if wallet.status != WalletStatus.ACTIVE:
            raise ValidationError(f"The user's {currency} account is {wallet.status.value.lower()} and cannot receive loan funds.")
        return wallet

    def _application_public(
        self,
        application: CreditApplication,
        documents: list[CreditDocument],
    ) -> CreditApplicationPublic:
        return CreditApplicationPublic(
            id=application.id,
            user_id=application.user_id,
            type=application.type,
            loan_product_type=application.loan_product_type,
            requested_amount=application.requested_amount,
            currency=application.currency,
            requested_term_months=application.requested_term_months,
            offered_interest_rate=application.offered_interest_rate,
            offered_amount=application.offered_amount,
            credit_score_at_application=application.credit_score_at_application,
            status=application.status,
            created_at=application.created_at,
            resolved_at=application.resolved_at,
            documents=[CreditDocumentPublic.model_validate(document) for document in documents],
        )

    def _group_documents_by_application(
        self,
        applications: list[CreditApplication],
        documents: list[CreditDocument],
    ) -> dict[uuid.UUID, list[CreditDocument]]:
        grouped: dict[uuid.UUID, list[CreditDocument]] = {}
        for document in documents:
            application_id = document.application_id or self._infer_application_for_document(document, applications)
            if application_id is None:
                continue
            grouped.setdefault(application_id, []).append(document)
        return grouped

    def _infer_application_for_document(
        self,
        document: CreditDocument,
        applications: list[CreditApplication],
    ) -> uuid.UUID | None:
        if document.purpose != CreditDocumentPurpose.LOAN_APPLICATION:
            return None
        same_user_applications = [application for application in applications if application.user_id == document.user_id]
        if not same_user_applications:
            return None
        candidates = [
            application
            for application in same_user_applications
            if _document_matches_application_product(document, application)
        ] or same_user_applications
        return min(candidates, key=lambda application: abs((document.uploaded_at - application.created_at).total_seconds())).id


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        is_leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if is_leap else 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31


def _simulate_fixed_payment_payoff(
    principal: Decimal,
    annual_interest_rate: Decimal,
    monthly_payment: Decimal,
) -> tuple[int, Decimal]:
    schedule = _fixed_payment_payoff_schedule(principal, annual_interest_rate, monthly_payment)
    return len(schedule), _money(sum((item[2] for item in schedule), Decimal("0.00")))


def _fixed_payment_payoff_schedule(
    principal: Decimal,
    annual_interest_rate: Decimal,
    monthly_payment: Decimal,
) -> list[tuple[Decimal, Decimal, Decimal, Decimal]]:
    remaining = _money(principal)
    if remaining == 0:
        return []
    if monthly_payment <= 0:
        raise ValidationError("Loan monthly payment must be positive")

    monthly_rate = annual_interest_rate / Decimal("100") / Decimal("12")
    schedule: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
    while remaining > 0:
        interest_amount = _money(remaining * monthly_rate)
        payment_amount = monthly_payment
        principal_amount = _money(payment_amount - interest_amount)
        if principal_amount <= 0:
            raise ValidationError("Monthly payment is too low to reduce principal")
        if principal_amount > remaining:
            principal_amount = remaining
            payment_amount = _money(principal_amount + interest_amount)
        remaining = _money(remaining - principal_amount)
        schedule.append((payment_amount, principal_amount, interest_amount, remaining))
    return schedule


def _remaining_interest_for_fixed_payment(
    principal: Decimal,
    annual_interest_rate: Decimal,
    monthly_payment: Decimal,
) -> Decimal:
    return _simulate_fixed_payment_payoff(principal, annual_interest_rate, monthly_payment)[1]


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError("Currency must be a 3-letter ISO code")
    return currency


def _document_matches_application_product(document: CreditDocument, application: CreditApplication) -> bool:
    if application.loan_product_type is None:
        return False
    product_name = get_loan_product(application.loan_product_type).name
    document_type = _normalize_match_text(document.document_type)
    product = _normalize_match_text(product_name)
    return product in document_type or document_type.replace("documentation", "").strip() in product


def _normalize_match_text(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("-", " ").lower().split())
