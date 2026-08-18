from decimal import Decimal

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.credit.models import CreditApplicationStatus, CreditApplicationType
from app.credit.schemas import CreditApplicationCreate, CreditScoreRecalculateRequest
from app.credit.scoring import calculate_credit_score, credit_band
from app.credit.service import CreditService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


def _create_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(
            email="credit-owner@example.com",
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
        CreditScoreRecalculateRequest(income=Decimal("12000.00"), existing_debt=Decimal("2000.00")),
    )
    profile = service.get_or_create_profile(user.id)

    assert score.score == 684
    assert score.band == "GOOD"
    assert profile.income == Decimal("12000.00")
    assert profile.existing_debt == Decimal("2000.00")
    assert len(profile.score_history) == 1


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
    assert application.credit_score_at_application == 644


def test_create_credit_card_application_allows_missing_term(db_session):
    user = _create_user(db_session)

    application = CreditService(db_session).create_application(
        user.id,
        CreditApplicationCreate(type=CreditApplicationType.CREDIT_CARD, requested_amount=Decimal("10000.00")),
    )

    assert application.type == CreditApplicationType.CREDIT_CARD
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
    assert body["status"] == "PENDING"
    assert body["credit_score_at_application"] == 600
