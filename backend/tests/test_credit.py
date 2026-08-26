from decimal import Decimal
from uuid import UUID

import pytest

from app.cards.models import CardType
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import NotFoundError, ValidationError
from app.core.enums import UserRole
from app.credit.loan_calculator import calculate_loan_schedule
from app.credit.models import (
    CreditApplicationStatus,
    CreditApplicationType,
    CreditDocumentPurpose,
    CreditDocumentStatus,
    LoanInstallmentStatus,
    LoanProductType,
    LoanStatus,
)
from app.credit.schemas import (
    CreditApplicationCreate,
    CreditApplicationDocumentCreate,
    CreditApplicationDecision,
    CreditDocumentCreate,
    CreditDocumentReview,
    CreditScoreRecalculateRequest,
    LoanCalculatorRequest,
)
from app.credit.scoring import calculate_credit_score, credit_band
from app.credit.service import CreditService
from app.notifications.service import NotificationsService
from app.transactions.models import LedgerEntryType, Transaction, TransactionType, WalletLedgerEntry
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.models import WalletStatus
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


def _create_user(db_session, email="credit-owner@example.com"):
    return UserService(db_session).create_user(
        UserCreate(
            email=email,
            password="Sup3rSecret!",
            first_name="Credit",
            last_name="Owner",
        )
    )


def _approve_application(
    application,
    amount: Decimal | None = None,
    rate: Decimal = Decimal("12.00"),
):
    application.status = CreditApplicationStatus.APPROVED
    application.offered_amount = amount or application.requested_amount
    application.offered_interest_rate = rate
    return application


def test_calculate_credit_score_is_deterministic_and_bounded():
    score, factors = calculate_credit_score(
        income=Decimal("1000000.00"),
        existing_debt=Decimal("0.00"),
        wallet_balance=Decimal("1000000.00"),
    )

    assert score == 850
    assert factors["income_factor"] == 240
    assert factors["wallet_balance_factor"] == 90
    assert credit_band(score) == "EXCELLENT"


def test_high_income_credit_score_handles_debt_proportionally():
    score, factors = calculate_credit_score(
        income=Decimal("3000000.00"),
        existing_debt=Decimal("250000.00"),
        wallet_balance=Decimal("0.00"),
    )

    assert score == 839
    assert factors["income_factor"] == 240
    assert factors["existing_debt_penalty"] == 1
    assert credit_band(score) == "EXCELLENT"


def test_get_or_create_profile_persists_initial_score_history(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("5000.00")

    profile = CreditService(db_session).get_or_create_profile(user.id)
    score = CreditService(db_session).get_score(user.id)

    assert profile.user_id == user.id
    assert profile.current_score == 613
    assert profile.currency == "RON"
    assert score.score == 613
    assert score.band == "FAIR"
    assert score.reason_data["wallet_balance"] == "5000.00"


def test_recalculate_score_updates_profile_inputs_without_publishing_score(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("10000.00")
    service = CreditService(db_session)

    score = service.recalculate_score(
        user.id,
        CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("2000.00"), currency="eur"),
    )
    profile = service.get_or_create_profile(user.id)

    assert score.score == 721
    assert score.band == "GOOD"
    assert profile.income == Decimal("12000.00")
    assert profile.existing_debt == Decimal("0.00")
    assert profile.currency == "EUR"
    assert score.reason_data["profile_currency"] == "EUR"
    assert score.reason_data["existing_debt_penalty"] == 0
    assert score.reason_data["review_status"] == "PENDING_ADMIN_REVIEW"
    assert profile.current_score == 600
    assert len(profile.score_history) == 0


def test_recalculate_score_rejects_invalid_currency(db_session):
    user = _create_user(db_session)

    with pytest.raises(ValidationError):
        CreditService(db_session).recalculate_score(
            user.id,
            CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("2000.00"), currency="EURO"),
        )


def test_recalculate_score_uses_active_loan_debt(db_session):
    user = _create_user(db_session, email="loan-debt-score@example.com")
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("10000.00")
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("25000.00"),
            requested_term_months=36,
        ),
    )
    _approve_application(application, Decimal("20000.00"), Decimal("9.50"))
    service.create_loan_from_application(user.id, application.id)
    foreign_currency_application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("5000.00"),
            currency="USD",
            requested_term_months=24,
        ),
    )
    _approve_application(foreign_currency_application, Decimal("5000.00"), Decimal("8.50"))
    service.create_loan_from_application(user.id, foreign_currency_application.id)

    score = service.recalculate_score(
        user.id,
        CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("999.00"), currency="RON"),
    )
    profile = service.get_or_create_profile(user.id)

    assert profile.existing_debt == Decimal("25000.00")
    assert score.reason_data["existing_debt"] == "25000.00"
    assert score.reason_data["absolute_debt_penalty"] == 0
    assert score.reason_data["debt_burden_penalty"] == 31
    assert score.reason_data["existing_debt_penalty"] == 31
    assert score.score == 690


def test_credit_score_endpoint_requires_auth(client):
    response = client.get("/api/v1/credit/score")

    assert response.status_code == 401


def test_credit_score_endpoint_returns_score(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "credit-endpoint@example.com",
            "password": "Sup3rSecret!",
            "first_name": "Credit",
            "last_name": "Endpoint",
        },
    )
    token = register.json()["tokens"]["access_token"]

    response = client.get("/api/v1/credit/score", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 600
    assert body["band"] == "FAIR"


def test_credit_profile_endpoint_returns_currency(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "credit-profile-endpoint@example.com",
            "password": "Sup3rSecret!",
            "first_name": "Credit",
            "last_name": "Profile",
        },
    )
    token = register.json()["tokens"]["access_token"]

    response = client.get("/api/v1/credit/profile", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["currency"] == "RON"


def test_loan_calculator_builds_deterministic_amortization_schedule():
    result = calculate_loan_schedule(
        LoanCalculatorRequest(
            principal_amount=Decimal("10000.00"),
            annual_interest_rate=Decimal("12.00"),
            term_months=12,
        )
    )

    assert result.monthly_payment == Decimal("888.49")
    assert result.currency == "RON"
    assert result.total_payment == sum((item.payment_amount for item in result.schedule), Decimal("0.00"))
    assert result.total_interest == sum((item.interest_amount for item in result.schedule), Decimal("0.00"))
    assert len(result.schedule) == 12
    assert result.schedule[0].interest_amount == Decimal("100.00")
    assert result.schedule[0].principal_amount == Decimal("788.49")
    assert result.schedule[-1].remaining_principal == Decimal("0.00")


def test_loan_calculator_supports_zero_interest():
    result = calculate_loan_schedule(
        LoanCalculatorRequest(
            principal_amount=Decimal("1200.00"),
            annual_interest_rate=Decimal("0.00"),
            term_months=12,
        )
    )

    assert result.monthly_payment == Decimal("100.00")
    assert result.total_payment == Decimal("1200.00")
    assert result.total_interest == Decimal("0.00")


def test_loan_calculator_rejects_invalid_inputs():
    with pytest.raises(ValidationError):
        calculate_loan_schedule(
            LoanCalculatorRequest(
                principal_amount=Decimal("0.00"),
                annual_interest_rate=Decimal("12.00"),
                term_months=12,
            )
        )

    with pytest.raises(ValidationError):
        calculate_loan_schedule(
            LoanCalculatorRequest(
                principal_amount=Decimal("1000.00"),
                annual_interest_rate=Decimal("-1.00"),
                term_months=12,
            )
        )

    with pytest.raises(ValidationError):
        calculate_loan_schedule(
            LoanCalculatorRequest(
                principal_amount=Decimal("1000.00"),
                currency="EURO",
                annual_interest_rate=Decimal("12.00"),
                term_months=12,
            )
        )

    with pytest.raises(ValidationError):
        calculate_loan_schedule(
            LoanCalculatorRequest(
                principal_amount=Decimal("1000.00"),
                annual_interest_rate=Decimal("12.00"),
                term_months=0,
            )
        )


def test_loan_calculator_endpoint_requires_auth(client):
    response = client.post(
        "/api/v1/credit/loan-calculator",
        json={"principal_amount": "10000.00", "annual_interest_rate": "12.00", "term_months": 12},
    )

    assert response.status_code == 401


def test_loan_calculator_endpoint_returns_schedule(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "credit-calculator-endpoint@example.com",
            "password": "Sup3rSecret!",
            "first_name": "Credit",
            "last_name": "Calculator",
        },
    )
    token = register.json()["tokens"]["access_token"]

    response = client.post(
        "/api/v1/credit/loan-calculator",
        headers={"Authorization": f"Bearer {token}"},
        json={"principal_amount": "10000.00", "annual_interest_rate": "12.00", "term_months": 12},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["monthly_payment"] == "888.49"
    assert body["currency"] == "RON"
    assert len(body["schedule"]) == 12
    assert body["schedule"][-1]["remaining_principal"] == "0.00"


def test_create_personal_loan_application_captures_current_score(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    service.recalculate_score(
        user.id,
        CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("2000.00")),
    )

    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("50000.00"),
            requested_term_months=48,
        ),
    )

    assert application.user_id == user.id
    assert application.status == CreditApplicationStatus.PENDING
    assert application.offered_amount is None
    assert application.offered_interest_rate is None
    assert application.resolved_at is None
    assert application.loan_product_type == LoanProductType.PERSONAL_LOAN
    assert application.credit_score_at_application == 696
    assert application.currency == "RON"

    notifications = NotificationsService(db_session).list_for_user(user.id)
    credit_notifications = [n for n in notifications if n.type == "CREDIT"]
    assert credit_notifications == []


def test_create_personal_loan_application_accepts_loan_product_type(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)

    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            loan_product_type=LoanProductType.MORTGAGE,
            requested_amount=Decimal("500000.00"),
            requested_term_months=240,
        ),
    )

    assert application.type == CreditApplicationType.PERSONAL_LOAN
    assert application.loan_product_type == LoanProductType.MORTGAGE
    assert application.status == CreditApplicationStatus.PENDING
    assert application.offered_amount is None
    assert application.offered_interest_rate is None

    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    _approve_application(application, Decimal("500000.00"), Decimal("6.80"))
    loan = service.create_loan_from_application(user.id, application.id)

    assert loan.loan_product_type == LoanProductType.MORTGAGE
    assert loan.interest_rate == Decimal("6.80")


def test_create_application_accepts_currency(db_session):
    user = _create_user(db_session)

    application = CreditService(db_session).create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("50000.00"),
            currency="eur",
            requested_term_months=48,
        ),
    )

    assert application.currency == "EUR"


def test_create_application_rejects_invalid_currency(db_session):
    user = _create_user(db_session)

    with pytest.raises(ValidationError):
        CreditService(db_session).create_application(
            user.id,
            CreditApplicationCreate(
                type=CreditApplicationType.PERSONAL_LOAN,
                requested_amount=Decimal("50000.00"),
                currency="EURO",
                requested_term_months=48,
            ),
        )


def test_create_credit_card_application_allows_missing_term(db_session):
    user = _create_user(db_session)

    application = CreditService(db_session).create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("10000.00")),
    )

    assert application.type == CreditApplicationType.CREDIT_CARD
    assert application.loan_product_type is None
    assert application.requested_term_months is None


def test_create_application_rejects_invalid_amount(db_session):
    user = _create_user(db_session)

    with pytest.raises(ValidationError):
        CreditService(db_session).create_application(
            user.id,
            CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("0.00")),
        )


def test_create_personal_loan_application_requires_term(db_session):
    user = _create_user(db_session)

    with pytest.raises(ValidationError):
        CreditService(db_session).create_application(
            user.id,
            CreditApplicationCreate(
                type=CreditApplicationType.PERSONAL_LOAN,
                requested_amount=Decimal("50000.00"),
            ),
        )


def test_list_and_get_applications_are_scoped_to_user(db_session):
    user = _create_user(db_session)
    other = UserService(db_session).create_user(
        UserCreate(
            email="credit-other@example.com",
            password="Sup3rSecret!",
            first_name="Credit",
            last_name="Other",
        )
    )
    service = CreditService(db_session)
    own = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("10000.00")),
    )
    other_application = service.create_application(
        other.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("15000.00")),
    )

    assert service.list_applications(user.id) == [own]
    assert service.get_application_for_user(user.id, own.id) == own
    with pytest.raises(NotFoundError):
        service.get_application_for_user(user.id, other_application.id)


def test_create_credit_application_endpoint(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "credit-application-endpoint@example.com",
            "password": "Sup3rSecret!",
            "first_name": "Credit",
            "last_name": "Application",
        },
    )
    token = register.json()["tokens"]["access_token"]

    response = client.post(
        "/api/v1/credit/applications",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": "CREDIT_CARD", "requested_amount": "12000.00"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "CREDIT_CARD"
    assert body["loan_product_type"] is None
    assert body["status"] == "PENDING"
    assert body["currency"] == "RON"
    assert body["credit_score_at_application"] == 600


def test_create_loan_application_endpoint_accepts_product_type(client, db_session):
    admin = _create_user(db_session, email="loan-product-admin@example.com")
    admin.role = UserRole.ADMIN
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "loan-product-application-endpoint@example.com",
            "password": "Sup3rSecret!",
            "first_name": "Loan",
            "last_name": "Product",
        },
    )
    token = register.json()["tokens"]["access_token"]

    response = client.post(
        "/api/v1/credit/applications",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "type": "PERSONAL_LOAN",
            "loan_product_type": "AUTO_LOAN",
            "requested_amount": "45000.00",
            "requested_term_months": 60,
            "documents": [
                {
                    "document_type": "Auto loan documentation",
                    "file_name": "auto-invoice.pdf",
                    "content_type": "application/pdf",
                    "file_size": 5,
                    "content_base64": "ZHVtbXk=",
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "PERSONAL_LOAN"
    assert body["loan_product_type"] == "AUTO_LOAN"
    assert body["status"] == "PENDING"
    assert body["offered_amount"] is None
    assert body["offered_interest_rate"] is None
    assert body["documents"][0]["file_name"] == "auto-invoice.pdf"

    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "loan-product-admin@example.com", "password": "Sup3rSecret!"},
    )
    admin_token = admin_login.json()["tokens"]["access_token"]
    admin_response = client.get(
        "/api/v1/credit/admin/applications",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert admin_response.status_code == 200
    admin_application = next(application for application in admin_response.json() if application["id"] == body["id"])
    assert admin_application["documents"][0]["file_name"] == "auto-invoice.pdf"


def test_create_loan_from_approved_application(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("25000.00"),
            requested_term_months=36,
        ),
    )
    _approve_application(application, Decimal("20000.00"), Decimal("9.50"))

    loan = service.create_loan_from_application(user.id, application.id)

    assert loan.user_id == user.id
    assert loan.application_id == application.id
    assert loan.principal_amount == Decimal("20000.00")
    assert loan.currency == "RON"
    assert loan.interest_rate == Decimal("9.50")
    assert loan.term_months == 36
    assert loan.monthly_payment == Decimal("640.66")
    assert loan.outstanding_principal == Decimal("20000.00")
    assert loan.status == LoanStatus.ACTIVE
    assert loan.start_date is not None
    assert loan.next_payment_date is not None
    assert loan.maturity_date is not None

    installments = service.list_installments_for_loan(user.id, loan.id)
    assert len(installments) == 36
    assert installments[0].installment_number == 1
    assert installments[0].status == LoanInstallmentStatus.PENDING
    assert installments[0].payment_amount == Decimal("640.66")
    assert installments[-1].remaining_principal == Decimal("0.00")
    assert wallet.available_balance == Decimal("20000.00")

    transaction = db_session.query(Transaction).filter_by(destination_wallet_id=wallet.id).one()
    assert transaction.type == TransactionType.TRANSFER
    assert transaction.status.value == "COMPLETED"
    assert transaction.description == "Personal loan disbursement"
    borrower_transactions = TransactionService(db_session).list_for_user(user.id)
    assert transaction.id in {item.id for item in borrower_transactions}

    ledger_entry = db_session.query(WalletLedgerEntry).filter_by(transaction_id=transaction.id).one()
    assert ledger_entry.entry_type == LedgerEntryType.CREDIT
    assert ledger_entry.amount == Decimal("20000.00")
    assert ledger_entry.balance_after == Decimal("20000.00")


def test_create_loan_creates_matching_currency_account_when_missing(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("20000.00"),
            currency="EUR",
            requested_term_months=36,
        ),
    )
    _approve_application(application, Decimal("20000.00"), Decimal("9.50"))

    loan = service.create_loan_from_application(user.id, application.id)
    wallet = WalletService(db_session).list_wallets(user.id)[0]

    assert loan.currency == "EUR"
    assert wallet.currency == "EUR"
    assert wallet.status == WalletStatus.ACTIVE
    assert wallet.available_balance == Decimal("20000.00")


def test_list_loans_does_not_repair_missing_disbursement_transaction_history(db_session):
    user = _create_user(db_session, email="missing-disbursement-history@example.com")
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("12000.00"),
            requested_term_months=24,
        ),
    )
    _approve_application(application, Decimal("12000.00"), Decimal("8.50"))
    loan = service.create_loan_from_application(user.id, application.id)
    transaction = db_session.query(Transaction).filter_by(destination_wallet_id=wallet.id).one()
    db_session.query(WalletLedgerEntry).filter_by(transaction_id=transaction.id).delete()
    db_session.delete(transaction)
    db_session.flush()

    loans = service.list_loans(user.id)
    borrower_transactions = TransactionService(db_session).list_for_user(user.id)

    assert loans == [loan]
    assert [item for item in borrower_transactions if item.description == "Personal loan disbursement"] == []
    assert wallet.available_balance == Decimal("12000.00")


def test_create_loan_rejects_frozen_matching_currency_account(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="EUR"))
    wallet.status = WalletStatus.FROZEN
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("20000.00"),
            currency="EUR",
            requested_term_months=36,
        ),
    )
    _approve_application(application, Decimal("20000.00"), Decimal("9.50"))

    with pytest.raises(ValidationError, match="frozen"):
        service.create_loan_from_application(user.id, application.id)


def test_simulate_early_repayment_shortens_term_and_saves_interest(db_session):
    user = _create_user(db_session)
    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("9.90"))
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)

    result = service.simulate_early_repayment(user.id, loan.id, Decimal("1000.00"))

    assert result.loan_id == loan.id
    assert result.currency == "RON"
    assert result.original_outstanding_principal == Decimal("10000.00")
    assert result.extra_payment_amount == Decimal("1000.00")
    assert result.applied_extra_payment_amount == Decimal("1000.00")
    assert result.new_outstanding_principal == Decimal("9000.00")
    assert result.remaining_term_months == 12
    assert result.revised_term_months < result.remaining_term_months
    assert result.term_months_reduced == result.remaining_term_months - result.revised_term_months
    assert result.total_interest_saved > Decimal("0.00")
    assert result.total_interest_after < result.total_interest_before


def test_simulate_early_repayment_rejects_invalid_amount(db_session):
    user = _create_user(db_session)
    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)

    with pytest.raises(ValidationError):
        service.simulate_early_repayment(user.id, loan.id, Decimal("0.00"))


def test_make_early_repayment_debits_wallet_and_reduces_loan(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("5000.00")
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)

    result = service.make_early_repayment(user.id, loan.id, wallet.id, Decimal("1000.00"))

    assert result.loan_id == loan.id
    assert result.transaction_id is not None
    assert result.loan_status == LoanStatus.ACTIVE
    assert result.applied_extra_payment_amount == Decimal("1000.00")
    assert result.new_outstanding_principal == Decimal("9000.00")
    assert loan.outstanding_principal == Decimal("9000.00")
    assert wallet.available_balance == Decimal("14000.00")

    transaction = db_session.get(Transaction, result.transaction_id)
    assert transaction is not None
    assert transaction.type == TransactionType.LOAN_PAYMENT
    assert transaction.source_wallet_id == wallet.id

    ledger_entry = (
        db_session.query(WalletLedgerEntry)
        .filter_by(transaction_id=result.transaction_id, entry_type=LedgerEntryType.DEBIT)
        .one()
    )
    assert ledger_entry.amount == Decimal("1000.00")
    assert ledger_entry.balance_after == Decimal("14000.00")


def test_make_early_repayment_from_debit_card_tags_card_transaction(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("5000.00")
    debit_card = CardService(db_session).create_card(
        user.id,
        CardCreate(type="DEBIT", tier="REGULAR", default_wallet_id=wallet.id),
    )
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)

    result = service.make_early_repayment(user.id, loan.id, wallet.id, Decimal("1000.00"), debit_card.id)

    transaction = db_session.get(Transaction, result.transaction_id)
    assert transaction is not None
    assert transaction.card_id == debit_card.id
    assert transaction.source_wallet_id == wallet.id
    assert transaction.type == TransactionType.LOAN_PAYMENT
    assert wallet.available_balance == Decimal("14000.00")


def test_admin_decides_credit_application(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("25000.00")),
    )

    decided = service.decide_application(
        application.id,
        CreditApplicationDecision(
            status=CreditApplicationStatus.APPROVED,
            offered_amount=Decimal("20000.00"),
            offered_interest_rate=Decimal("9.50"),
        ),
    )

    assert decided.status == CreditApplicationStatus.APPROVED
    assert decided.offered_amount == Decimal("20000.00")
    assert decided.offered_interest_rate == Decimal("9.50")
    assert decided.resolved_at is not None
    issued_cards = CardService(db_session).list_cards(user.id)
    assert len(issued_cards) == 1
    assert issued_cards[0].type == CardType.CREDIT
    assert issued_cards[0].credit_account is not None
    assert issued_cards[0].credit_account.credit_limit == Decimal("20000.00")
    assert issued_cards[0].credit_account.annual_interest_rate == Decimal("9.50")
    assert issued_cards[0].credit_account.collateral_wallet_id is None

    credit_notifications = [
        n for n in NotificationsService(db_session).list_for_user(user.id) if n.type == "CREDIT"
    ]
    assert len(credit_notifications) == 1
    assert "approved" in credit_notifications[0].title.lower()


def test_admin_loan_decision_uses_submitted_amount_and_product_rate(db_session):
    user = _create_user(db_session)
    admin = _create_user(db_session, email="loan-document-admin@example.com")
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            loan_product_type=LoanProductType.MORTGAGE,
            requested_amount=Decimal("190000.00"),
            requested_term_months=240,
            documents=[
                CreditApplicationDocumentCreate(
                    document_type="Mortgage documentation",
                    file_name="valuation.pdf",
                    file_size=13,
                    content_base64="dmFsdWF0aW9uLnBkZg==",
                ),
            ],
        ),
    )

    decided = service.decide_application(
        application.id,
        CreditApplicationDecision(
            status=CreditApplicationStatus.APPROVED,
            offered_amount=Decimal("1.00"),
            offered_interest_rate=Decimal("99.00"),
        ),
        admin_id=admin.id,
    )

    assert decided.status == CreditApplicationStatus.APPROVED
    assert decided.offered_amount == Decimal("190000.00")
    assert decided.offered_interest_rate == Decimal("6.80")
    assert decided.resolved_at is not None
    wallet = WalletService(db_session).list_wallets(user.id)[0]
    assert wallet.currency == "RON"
    assert wallet.available_balance == Decimal("190000.00")

    loan = service.create_loan_from_application(user.id, application.id)
    assert loan.principal_amount == Decimal("190000.00")
    assert wallet.available_balance == Decimal("190000.00")
    public_application = service.get_application_public(application.id)
    assert public_application.documents[0].file_name == "valuation.pdf"
    assert public_application.documents[0].status == CreditDocumentStatus.APPROVED
    assert public_application.documents[0].reviewed_by_admin_id == admin.id


def test_admin_rejection_notifies_the_applicant(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("25000.00")),
    )

    service.decide_application(application.id, CreditApplicationDecision(status=CreditApplicationStatus.REJECTED))

    credit_notifications = [
        n for n in NotificationsService(db_session).list_for_user(user.id) if n.type == "CREDIT"
    ]
    assert len(credit_notifications) == 1
    assert "rejected" in credit_notifications[0].title.lower()


def test_admin_decision_rejects_invalid_status_and_offer(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("5000.00")),
    )

    with pytest.raises(ValidationError):
        service.decide_application(
            application.id,
            CreditApplicationDecision(status=CreditApplicationStatus.PENDING),
        )

    with pytest.raises(ValidationError):
        service.decide_application(
            application.id,
            CreditApplicationDecision(status=CreditApplicationStatus.APPROVED, offered_amount=Decimal("5000.00")),
        )


def test_create_loan_requires_approved_personal_loan_application(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    card_application = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("5000.00")),
    )
    card_application.status = CreditApplicationStatus.APPROVED
    card_application.offered_amount = Decimal("5000.00")
    card_application.offered_interest_rate = Decimal("18.00")

    with pytest.raises(ValidationError):
        service.create_loan_from_application(user.id, card_application.id)


def test_create_loan_is_idempotent_for_existing_application_loan(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    first_loan = service.create_loan_from_application(user.id, application.id)
    balance_after_first_disbursement = wallet.available_balance

    second_loan = service.create_loan_from_application(user.id, application.id)

    assert second_loan.id == first_loan.id
    assert wallet.available_balance == balance_after_first_disbursement


def test_list_and_get_loans_are_scoped_to_user(db_session):
    user = _create_user(db_session)
    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    other = UserService(db_session).create_user(
        UserCreate(
            email="loan-other@example.com",
            password="Sup3rSecret!",
            first_name="Loan",
            last_name="Other",
        )
    )
    WalletService(db_session).create_wallet(other.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    own_application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(own_application, Decimal("10000.00"), Decimal("12.00"))
    own_loan = service.create_loan_from_application(user.id, own_application.id)
    other_application = service.create_application(
        other.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("12000.00"),
            requested_term_months=24,
        ),
    )
    _approve_application(other_application, Decimal("12000.00"), Decimal("10.00"))
    other_loan = service.create_loan_from_application(other.id, other_application.id)

    assert service.list_loans(user.id) == [own_loan]
    assert service.get_loan_for_user(user.id, own_loan.id) == own_loan
    with pytest.raises(NotFoundError):
        service.get_loan_for_user(user.id, other_loan.id)


def test_loan_endpoints_require_auth(client):
    list_response = client.get("/api/v1/credit/loans")
    get_response = client.get("/api/v1/credit/loans/00000000-0000-0000-0000-000000000000")
    create_response = client.post("/api/v1/credit/applications/00000000-0000-0000-0000-000000000000/loan")
    installments_response = client.get("/api/v1/credit/loans/00000000-0000-0000-0000-000000000000/installments")

    assert list_response.status_code == 401
    assert get_response.status_code == 401
    assert create_response.status_code == 401
    assert installments_response.status_code == 401


def test_list_loans_endpoint_returns_user_loans(client, db_session):
    user = _create_user(db_session)
    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-owner@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    list_response = client.get("/api/v1/credit/loans", headers={"Authorization": f"Bearer {token}"})
    get_response = client.get(f"/api/v1/credit/loans/{loan.id}", headers={"Authorization": f"Bearer {token}"})

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == str(loan.id)
    assert get_response.status_code == 200
    assert get_response.json()["application_id"] == str(application.id)


def test_create_loan_endpoint_creates_installments(client, db_session):
    user = _create_user(db_session)
    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("9.90"))
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-owner@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    create_response = client.post(
        f"/api/v1/credit/applications/{application.id}/loan",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert create_response.status_code == 201
    loan_id = create_response.json()["id"]
    installments_response = client.get(
        f"/api/v1/credit/loans/{loan_id}/installments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert installments_response.status_code == 200
    installments = installments_response.json()
    assert len(installments) == 12
    assert installments[0]["payment_amount"] == "878.69"
    assert installments[-1]["remaining_principal"] == "0.00"


def test_early_repayment_simulation_endpoint_returns_contract(client, db_session):
    user = _create_user(db_session)
    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-owner@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    response = client.post(
        f"/api/v1/credit/loans/{loan.id}/early-repayment-simulation",
        headers={"Authorization": f"Bearer {token}"},
        json={"extra_payment_amount": "1000.00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["loan_id"] == str(loan.id)
    assert body["currency"] == "RON"
    assert body["original_outstanding_principal"] == "10000.00"
    assert body["extra_payment_amount"] == "1000.00"
    assert body["applied_extra_payment_amount"] == "1000.00"
    assert body["new_outstanding_principal"] == "9000.00"
    assert body["remaining_term_months"] == 12
    assert body["revised_term_months"] < body["remaining_term_months"]
    assert body["term_months_reduced"] == body["remaining_term_months"] - body["revised_term_months"]


def test_early_repayment_endpoint_pays_from_wallet(client, db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("5000.00")
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-owner@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    response = client.post(
        f"/api/v1/credit/loans/{loan.id}/early-repayment",
        headers={"Authorization": f"Bearer {token}"},
        json={"source_wallet_id": str(wallet.id), "amount": "1000.00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transaction_id"]
    assert body["loan_id"] == str(loan.id)
    assert body["loan_status"] == "ACTIVE"
    assert body["applied_extra_payment_amount"] == "1000.00"
    assert body["new_outstanding_principal"] == "9000.00"

    db_session.refresh(wallet)
    db_session.refresh(loan)
    assert wallet.available_balance == Decimal("14000.00")
    assert loan.outstanding_principal == Decimal("9000.00")


def test_early_repayment_endpoint_records_source_debit_card(client, db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("5000.00")
    debit_card = CardService(db_session).create_card(
        user.id,
        CardCreate(type="DEBIT", tier="REGULAR", default_wallet_id=wallet.id),
    )
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-owner@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    response = client.post(
        f"/api/v1/credit/loans/{loan.id}/early-repayment",
        headers={"Authorization": f"Bearer {token}"},
        json={"source_wallet_id": str(wallet.id), "source_card_id": str(debit_card.id), "amount": "1000.00"},
    )

    assert response.status_code == 200
    transaction = db_session.get(Transaction, UUID(response.json()["transaction_id"]))
    assert transaction is not None
    assert transaction.card_id == debit_card.id
    assert transaction.source_wallet_id == wallet.id


def test_early_repayment_endpoint_can_pay_from_credit_card(client, db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    credit_card = CardService(db_session).create_card(
        user.id,
        CardCreate(type="CREDIT", tier="REGULAR"),
    )
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    _approve_application(application, Decimal("10000.00"), Decimal("12.00"))
    loan = service.create_loan_from_application(user.id, application.id)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-owner@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    response = client.post(
        f"/api/v1/credit/loans/{loan.id}/early-repayment",
        headers={"Authorization": f"Bearer {token}"},
        json={"source_card_id": str(credit_card.id), "amount": "1000.00"},
    )

    assert response.status_code == 200
    transaction = db_session.get(Transaction, UUID(response.json()["transaction_id"]))
    assert transaction is not None
    assert transaction.card_id == credit_card.id
    assert transaction.source_wallet_id is None
    db_session.refresh(loan)
    assert loan.outstanding_principal == Decimal("9000.00")
    assert credit_card.credit_account is not None
    assert credit_card.credit_account.used_amount == Decimal("1000.00")


def test_admin_credit_application_endpoints_require_admin(client, db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("5000.00")),
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-owner@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    list_response = client.get("/api/v1/credit/admin/applications", headers={"Authorization": f"Bearer {token}"})
    decision_response = client.patch(
        f"/api/v1/credit/admin/applications/{application.id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "REJECTED"},
    )

    assert list_response.status_code == 403
    assert decision_response.status_code == 403


def test_admin_credit_application_endpoint_decides_application(client, db_session):
    user = _create_user(db_session, email="credit-user@example.com")
    admin = _create_user(db_session, email="credit-admin@example.com")
    admin.role = UserRole.ADMIN
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("10000.00")),
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "credit-admin@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["tokens"]["access_token"]

    response = client.patch(
        f"/api/v1/credit/admin/applications/{application.id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "APPROVED", "offered_amount": "9000.00", "offered_interest_rate": "10.00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["offered_amount"] == "9000.00"
    assert body["currency"] == "RON"
    assert body["offered_interest_rate"] == "10.00"
    assert body["resolved_at"] is not None


def test_credit_document_upload_and_admin_review_flow(client, db_session):
    user = _create_user(db_session, email="document-user@example.com")
    admin = _create_user(db_session, email="document-admin@example.com")
    admin.role = UserRole.ADMIN
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("12000.00"),
            requested_term_months=24,
        ),
    )
    user_login = client.post(
        "/api/v1/auth/login",
        json={"email": "document-user@example.com", "password": "Sup3rSecret!"},
    )
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "document-admin@example.com", "password": "Sup3rSecret!"},
    )
    user_token = user_login.json()["tokens"]["access_token"]
    admin_token = admin_login.json()["tokens"]["access_token"]

    upload_response = client.post(
        "/api/v1/credit/documents",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "application_id": str(application.id),
            "purpose": "LOAN_APPLICATION",
            "document_type": "Proof of income",
            "file_name": "salary.pdf",
            "content_type": "application/pdf",
            "file_size": 10,
            "content_base64": "c2FsYXJ5LXBkZg==",
        },
    )

    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    list_response = client.get("/api/v1/credit/admin/documents", headers={"Authorization": f"Bearer {admin_token}"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["file_name"] == "salary.pdf"

    applications_response = client.get("/api/v1/credit/admin/applications", headers={"Authorization": f"Bearer {admin_token}"})
    assert applications_response.status_code == 200
    application_body = next(item for item in applications_response.json() if item["id"] == str(application.id))
    assert application_body["documents"][0]["id"] == document_id
    assert application_body["documents"][0]["file_name"] == "salary.pdf"

    content_response = client.get(
        f"/api/v1/credit/admin/documents/{document_id}/content",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert content_response.status_code == 200
    assert content_response.json()["file_name"] == "salary.pdf"
    assert content_response.json()["content_base64"] == "c2FsYXJ5LXBkZg=="

    review_response = client.patch(
        f"/api/v1/credit/admin/documents/{document_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "APPROVED", "evaluation_score": 92, "review_note": "Income proof matches application."},
    )

    assert review_response.status_code == 200
    body = review_response.json()
    assert body["status"] == "APPROVED"
    assert body["evaluation_score"] == 92
    assert body["reviewed_by_admin_id"] == str(admin.id)


def test_credit_document_upload_rejects_invalid_content_size(db_session):
    user = _create_user(db_session, email="document-content-validation@example.com")
    service = CreditService(db_session)

    with pytest.raises(ValidationError):
        service.upload_document(
            user.id,
            CreditDocumentCreate(
                purpose=CreditDocumentPurpose.CREDIT_SCORE,
                document_type="Proof of income",
                file_name="salary.pdf",
                file_size=99,
                content_base64="c2FsYXJ5LXBkZg==",
            ),
        )


def test_loan_application_documents_must_be_linked_to_application(db_session):
    user = _create_user(db_session, email="document-validation@example.com")
    service = CreditService(db_session)

    with pytest.raises(ValidationError):
        service.upload_document(
            user.id,
            CreditDocumentCreate(
                purpose=CreditDocumentPurpose.LOAN_APPLICATION,
                document_type="Proof of income",
                file_name="salary.pdf",
                file_size=100,
            ),
        )


def test_document_review_rejects_uploaded_as_final_status(db_session):
    user = _create_user(db_session, email="document-review-validation@example.com")
    admin = _create_user(db_session, email="document-review-admin@example.com")
    service = CreditService(db_session)
    document = service.upload_document(
        user.id,
        CreditDocumentCreate(
            purpose=CreditDocumentPurpose.CREDIT_SCORE,
            document_type="Debt statement",
            file_name="debt.pdf",
            file_size=100,
        ),
    )

    with pytest.raises(ValidationError):
        service.review_document(
            document.id,
            admin.id,
            CreditDocumentReview(status=CreditDocumentStatus.UPLOADED),
        )


def test_request_application_more_info_marks_documents_and_notifies_user(db_session):
    user = _create_user(db_session, email="loan-more-info-user@example.com")
    admin = _create_user(db_session, email="loan-more-info-admin@example.com")
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            loan_product_type=LoanProductType.MORTGAGE,
            requested_amount=Decimal("120000.00"),
            currency="RON",
            requested_term_months=240,
            documents=[
                CreditApplicationDocumentCreate(
                    document_type="Property documents",
                    file_name="property.pdf",
                    file_size=12,
                    content_base64="cHJvcGVydHkucGRm",
                )
            ],
        ),
    )

    updated = service.request_application_more_info(application.id, admin_id=admin.id)
    documents = [document for document in service.list_documents(user.id) if document.application_id == application.id]
    notifications = [notification for notification in NotificationsService(db_session).list_for_user(user.id) if notification.type == "CREDIT"]

    assert updated.status == CreditApplicationStatus.PENDING
    assert documents
    assert {document.status for document in documents} == {CreditDocumentStatus.NEEDS_MORE_INFO}
    assert documents[0].review_note == "Additional supporting information required."
    assert len(notifications) == 1
    assert notifications[0].title == "More loan information required"
    assert "upload" in notifications[0].message.lower()


def test_credit_score_document_review_publishes_score_after_admin_approval(db_session):
    user = _create_user(db_session, email="score-review-user@example.com")
    admin = _create_user(db_session, email="score-review-admin@example.com")
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("10000.00")
    service = CreditService(db_session)

    provisional = service.recalculate_score(
        user.id,
        CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("2000.00"), currency="RON"),
    )
    document = service.upload_document(
        user.id,
        CreditDocumentCreate(
            purpose=CreditDocumentPurpose.CREDIT_SCORE,
            document_type="Income and debt documentation",
            file_name="salary.pdf",
            file_size=10,
            content_base64="c2FsYXJ5LnBkZg==",
        ),
    )
    profile = service.get_or_create_profile(user.id)

    assert provisional.score == 721
    assert document.evaluation_score == 721
    assert profile.current_score == 600
    assert len(profile.score_history) == 0

    reviewed = service.review_document(
        document.id,
        admin.id,
        CreditDocumentReview(status=CreditDocumentStatus.APPROVED, evaluation_score=document.evaluation_score),
    )

    assert reviewed.status == CreditDocumentStatus.APPROVED
    assert profile.current_score == 721
    latest_history = service.repository.latest_history(profile.id)
    assert latest_history is not None
    assert latest_history.score == 721


def test_credit_score_document_review_allows_admin_score_override(db_session):
    user = _create_user(db_session, email="score-review-override-user@example.com")
    admin = _create_user(db_session, email="score-review-override-admin@example.com")
    service = CreditService(db_session)
    service.recalculate_score(
        user.id,
        CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("0.00"), currency="RON"),
    )
    document = service.upload_document(
        user.id,
        CreditDocumentCreate(
            purpose=CreditDocumentPurpose.CREDIT_SCORE,
            document_type="Income and debt documentation",
            file_name="salary.pdf",
            file_size=10,
            content_base64="c2FsYXJ5LnBkZg==",
        ),
    )

    reviewed = service.review_document(
        document.id,
        admin.id,
        CreditDocumentReview(status=CreditDocumentStatus.APPROVED, evaluation_score=780),
    )
    profile = service.get_or_create_profile(user.id)

    assert reviewed.evaluation_score == 780
    assert profile.current_score == 780
    latest_history = service.repository.latest_history(profile.id)
    assert latest_history is not None
    assert latest_history.score == 780


def test_loan_products_endpoint_returns_disclosures(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "credit-products-endpoint@example.com",
            "password": "Sup3rSecret!",
            "first_name": "Credit",
            "last_name": "Products",
        },
    )
    token = register.json()["tokens"]["access_token"]

    response = client.get("/api/v1/credit/loan-products", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    products = response.json()
    product_types = {product["product_type"] for product in products}
    assert product_types == {
        "PERSONAL_LOAN",
        "MORTGAGE",
        "AUTO_LOAN",
        "STUDENT_LOAN",
        "HOME_IMPROVEMENT",
        "DEBT_CONSOLIDATION",
    }
    mortgage = next(product for product in products if product["product_type"] == "MORTGAGE")
    assert mortgage["collateral_required"] is True
    assert mortgage["representative_apr"] == "6.80"
    assert mortgage["obligations"]
    assert mortgage["liabilities"]
