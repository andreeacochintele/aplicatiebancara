"""Credit profile and score business rules."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import utcnow
from app.credit.loan_calculator import calculate_loan_schedule
from app.credit.models import (
    CreditApplication,
    CreditApplicationStatus,
    CreditApplicationType,
    CreditProfile,
    CreditScoreHistory,
    Loan,
    LoanInstallment,
    LoanProductType,
)
from app.credit.products import get_loan_product, list_loan_products
from app.credit.repository import CreditRepository
from app.credit.schemas import (
    CreditApplicationCreate,
    CreditApplicationDecision,
    LoanProductPublic,
    CreditScorePublic,
    CreditScoreRecalculateRequest,
    LoanCalculatorRequest,
    LoanCalculatorResult,
)
from app.credit.scoring import calculate_credit_score, credit_band
from app.notifications.models import NotificationType
from app.notifications.service import NotificationService
from app.wallets.repository import WalletRepository


class CreditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CreditRepository(db)
        self.wallets = WalletRepository(db)
        self.notifications = NotificationService(db)

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
        if data.existing_debt is not None:
            profile.existing_debt = data.existing_debt
        if data.currency is not None:
            profile.currency = _normalize_currency(data.currency)

        history = self._persist_score(profile, self._wallet_balance(user_id))
        return CreditScorePublic(
            score=profile.current_score,
            band=credit_band(profile.current_score),
            reason_data=history.reason_data,
            calculated_at=history.created_at,
        )

    def create_application(self, user_id: uuid.UUID, data: CreditApplicationCreate) -> CreditApplication:
        if data.requested_amount <= 0:
            raise ValidationError("Requested amount must be positive")
        currency = _normalize_currency(data.currency)
        if data.type == CreditApplicationType.PERSONAL_LOAN:
            loan_product_type = data.loan_product_type or LoanProductType.PERSONAL_LOAN
            if data.requested_term_months is None or data.requested_term_months <= 0:
                raise ValidationError("Personal loan applications require a positive term")
            loan_product = get_loan_product(loan_product_type)
            # Temporary no-admin demo path: restore manual review by setting this back to PENDING.
            status = CreditApplicationStatus.APPROVED
            offered_amount = data.requested_amount
            offered_interest_rate = loan_product.representative_apr
            resolved_at = utcnow()
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
        if status == CreditApplicationStatus.APPROVED:
            self.notifications.notify(
                user_id,
                NotificationType.CREDIT,
                "Credit application approved",
                f"Your application for {offered_amount} {currency} was approved at {offered_interest_rate}% APR.",
            )
        return application

    def calculate_loan(self, data: LoanCalculatorRequest) -> LoanCalculatorResult:
        return calculate_loan_schedule(data)

    def list_loan_products(self) -> list[LoanProductPublic]:
        return list_loan_products()

    def create_loan_from_application(self, user_id: uuid.UUID, application_id: uuid.UUID) -> Loan:
        application = self.get_application_for_user(user_id, application_id)
        if application.type != CreditApplicationType.PERSONAL_LOAN:
            raise ValidationError("Only personal loan applications can create loans")
        if application.status != CreditApplicationStatus.APPROVED:
            raise ValidationError("Only approved applications can create loans")
        if application.requested_term_months is None or application.requested_term_months <= 0:
            raise ValidationError("Approved loan applications require a positive term")
        if application.offered_amount is None or application.offered_amount <= 0:
            raise ValidationError("Approved loan applications require a positive offered amount")
        if application.offered_interest_rate is None or application.offered_interest_rate < 0:
            raise ValidationError("Approved loan applications require a non-negative offered interest rate")
        if self.repository.get_loan_by_application(application.id) is not None:
            raise ValidationError("Loan already exists for this application")

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

    def list_applications(self, user_id: uuid.UUID) -> list[CreditApplication]:
        return self.repository.list_applications_for_user(user_id)

    def list_all_applications(self) -> list[CreditApplication]:
        return self.repository.list_applications()

    def get_application_for_user(self, user_id: uuid.UUID, application_id: uuid.UUID) -> CreditApplication:
        application = self.repository.get_application_by_id(application_id)
        if application is None or application.user_id != user_id:
            raise NotFoundError("Credit application not found")
        return application

    def decide_application(self, application_id: uuid.UUID, data: CreditApplicationDecision) -> CreditApplication:
        application = self.repository.get_application_by_id(application_id)
        if application is None:
            raise NotFoundError("Credit application not found")
        if application.status not in {CreditApplicationStatus.PENDING, CreditApplicationStatus.DRAFT}:
            raise ValidationError("Only draft or pending applications can be decided")
        if data.status not in {CreditApplicationStatus.APPROVED, CreditApplicationStatus.REJECTED}:
            raise ValidationError("Credit applications can only be approved or rejected")

        if data.status == CreditApplicationStatus.APPROVED:
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
        if data.status == CreditApplicationStatus.APPROVED:
            self.notifications.notify(
                application.user_id,
                NotificationType.CREDIT,
                "Credit application approved",
                f"Your application for {application.offered_amount} {application.currency} was approved "
                f"at {application.offered_interest_rate}% APR.",
            )
        else:
            self.notifications.notify(
                application.user_id,
                NotificationType.CREDIT,
                "Credit application rejected",
                f"Your application for {application.requested_amount} {application.currency} was rejected.",
            )
        self.db.flush()
        return application

    def _wallet_balance(self, user_id: uuid.UUID) -> Decimal:
        return sum((wallet.available_balance for wallet in self.wallets.list_for_user(user_id)), Decimal("0"))

    def _persist_score(self, profile: CreditProfile, wallet_balance: Decimal) -> CreditScoreHistory:
        score, factors = calculate_credit_score(profile.income, profile.existing_debt, wallet_balance)
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


def _normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError("Currency must be a 3-letter ISO code")
    return currency
