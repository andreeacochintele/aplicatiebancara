from decimal import Decimal

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.core.enums import UserRole
from app.credit.loan_calculator import calculate_loan_schedule
from app.credit.models import (
    CreditApplicationStatus,
    CreditApplicationType,
    LoanInstallmentStatus,
    LoanProductType,
    LoanStatus,
)
from app.credit.schemas import (
    CreditApplicationCreate,
    CreditApplicationDecision,
    CreditScoreRecalculateRequest,
    LoanCalculatorRequest,
)
from app.credit.scoring import calculate_credit_score, credit_band
from app.credit.service import CreditService
from app.notifications.models import NotificationType
from app.notifications.service import NotificationService
from app.users.schemas import UserCreate
from app.users.service import UserService
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


def test_calculate_credit_score_is_deterministic_and_bounded():
    score, factors = calculate_credit_score(
        income=Decimal("1000000.00"),
        existing_debt=Decimal("0.00"),
        wallet_balance=Decimal("1000000.00"),
    )

    assert score == 800
    assert factors["income_factor"] == 120
    assert factors["wallet_balance_factor"] == 80
    assert credit_band(score) == "EXCELLENT"


def test_get_or_create_profile_persists_initial_score_history(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("5000.00")

    profile = CreditService(db_session).get_or_create_profile(user.id)
    score = CreditService(db_session).get_score(user.id)

    assert profile.user_id == user.id
    assert profile.current_score == 620
    assert profile.currency == "RON"
    assert score.score == 620
    assert score.band == "FAIR"
    assert score.reason_data["wallet_balance"] == "5000.00"


def test_recalculate_score_updates_mock_profile_inputs_and_history(db_session):
    user = _create_user(db_session)
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("10000.00")
    service = CreditService(db_session)

    score = service.recalculate_score(
        user.id,
        CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("2000.00"), currency="eur"),
    )
    profile = service.get_or_create_profile(user.id)

    assert score.score == 684
    assert score.band == "GOOD"
    assert profile.income == Decimal("12000.00")
    assert profile.existing_debt == Decimal("2000.00")
    assert profile.currency == "EUR"
    assert score.reason_data["profile_currency"] == "EUR"
    assert len(profile.score_history) == 1


def test_recalculate_score_rejects_invalid_currency(db_session):
    user = _create_user(db_session)

    with pytest.raises(ValidationError):
        CreditService(db_session).recalculate_score(
            user.id,
            CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("2000.00"), currency="EURO"),
        )


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
    assert application.status == CreditApplicationStatus.APPROVED
    assert application.offered_amount == Decimal("50000.00")
    assert application.offered_interest_rate == Decimal("9.90")
    assert application.resolved_at is not None
    assert application.loan_product_type == LoanProductType.PERSONAL_LOAN
    assert application.credit_score_at_application == 644
    assert application.currency == "RON"

    notifications = NotificationService(db_session).list_for_user(user.id)
    credit_notifications = [n for n in notifications if n.type == NotificationType.CREDIT]
    assert len(credit_notifications) == 1
    assert "approved" in credit_notifications[0].title.lower()


def test_create_personal_loan_application_accepts_loan_product_type(db_session):
    user = _create_user(db_session)

    application = CreditService(db_session).create_application(
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
    assert application.status == CreditApplicationStatus.APPROVED
    assert application.offered_amount == Decimal("500000.00")
    assert application.offered_interest_rate == Decimal("6.80")


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


def test_create_loan_application_endpoint_accepts_product_type(client):
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
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "PERSONAL_LOAN"
    assert body["loan_product_type"] == "AUTO_LOAN"
    assert body["status"] == "APPROVED"
    assert body["offered_amount"] == "45000.00"
    assert body["offered_interest_rate"] == "8.40"


def test_create_loan_from_approved_application(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("25000.00"),
            requested_term_months=36,
        ),
    )
    application.status = CreditApplicationStatus.APPROVED
    application.offered_amount = Decimal("20000.00")
    application.offered_interest_rate = Decimal("9.50")

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

    credit_notifications = [
        n for n in NotificationService(db_session).list_for_user(user.id) if n.type == NotificationType.CREDIT
    ]
    assert len(credit_notifications) == 1
    assert "approved" in credit_notifications[0].title.lower()


def test_admin_rejection_notifies_the_applicant(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("25000.00")),
    )

    service.decide_application(application.id, CreditApplicationDecision(status=CreditApplicationStatus.REJECTED))

    credit_notifications = [
        n for n in NotificationService(db_session).list_for_user(user.id) if n.type == NotificationType.CREDIT
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


def test_create_loan_rejects_duplicate_for_application(db_session):
    user = _create_user(db_session)
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    application.status = CreditApplicationStatus.APPROVED
    application.offered_amount = Decimal("10000.00")
    application.offered_interest_rate = Decimal("12.00")
    service.create_loan_from_application(user.id, application.id)

    with pytest.raises(ValidationError):
        service.create_loan_from_application(user.id, application.id)


def test_list_and_get_loans_are_scoped_to_user(db_session):
    user = _create_user(db_session)
    other = UserService(db_session).create_user(
        UserCreate(
            email="loan-other@example.com",
            password="Sup3rSecret!",
            first_name="Loan",
            last_name="Other",
        )
    )
    service = CreditService(db_session)
    own_application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    own_application.status = CreditApplicationStatus.APPROVED
    own_application.offered_amount = Decimal("10000.00")
    own_application.offered_interest_rate = Decimal("12.00")
    own_loan = service.create_loan_from_application(user.id, own_application.id)
    other_application = service.create_application(
        other.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("12000.00"),
            requested_term_months=24,
        ),
    )
    other_application.status = CreditApplicationStatus.APPROVED
    other_application.offered_amount = Decimal("12000.00")
    other_application.offered_interest_rate = Decimal("10.00")
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
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
    application.status = CreditApplicationStatus.APPROVED
    application.offered_amount = Decimal("10000.00")
    application.offered_interest_rate = Decimal("12.00")
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
    service = CreditService(db_session)
    application = service.create_application(
        user.id,
        CreditApplicationCreate(
            type=CreditApplicationType.PERSONAL_LOAN,
            requested_amount=Decimal("10000.00"),
            requested_term_months=12,
        ),
    )
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
