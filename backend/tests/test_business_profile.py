from datetime import date, timedelta

import pytest

from app.business.schemas import BusinessProfileCreate, BusinessProfileUpdate
from app.business.service import BusinessProfileService
from app.core.enums import UserType
from app.core.exceptions import NotFoundError
from app.statements.schemas import StatementRequest
from app.statements.service import StatementService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def business_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(
            email="biz-profile@example.com",
            phone="+40744444460",
            password="Sup3rSecret!",
            first_name="Biz",
            last_name="Owner",
            user_type=UserType.BUSINESS,
        )
    )


def test_get_active_profile_returns_none_before_creation(db_session, business_user):
    profile = BusinessProfileService(db_session).get_active_profile(business_user.id)
    assert profile is None


def test_first_created_profile_becomes_active_automatically(db_session, business_user):
    service = BusinessProfileService(db_session)
    profile = service.create_profile(
        business_user.id, BusinessProfileCreate(company_name="Acme SRL", tax_id="RO123", representative_name="Ion Pop")
    )

    assert profile.company_name == "Acme SRL"
    assert profile.is_active is True
    assert profile.representative_name == "Ion Pop"

    active = service.get_active_profile(business_user.id)
    assert active.id == profile.id


def test_second_company_does_not_become_active_automatically(db_session, business_user):
    service = BusinessProfileService(db_session)
    first = service.create_profile(business_user.id, BusinessProfileCreate(company_name="Acme SRL"))
    second = service.create_profile(business_user.id, BusinessProfileCreate(company_name="Beta SRL"))

    assert first.is_active is True
    assert second.is_active is False
    assert len(service.list_profiles(business_user.id)) == 2


def test_set_active_profile_switches_exclusively(db_session, business_user):
    service = BusinessProfileService(db_session)
    first = service.create_profile(business_user.id, BusinessProfileCreate(company_name="Acme SRL"))
    second = service.create_profile(business_user.id, BusinessProfileCreate(company_name="Beta SRL"))

    service.set_active_profile(business_user.id, second.id)

    profiles = {p.id: p for p in service.list_profiles(business_user.id)}
    assert profiles[first.id].is_active is False
    assert profiles[second.id].is_active is True


def test_set_active_profile_rejects_another_users_profile(db_session, business_user):
    other = UserService(db_session).create_user(
        UserCreate(
            email="biz-profile-other@example.com",
            phone="+40744444463",
            password="Sup3rSecret!",
            first_name="Other",
            last_name="Biz",
            user_type=UserType.BUSINESS,
        )
    )
    service = BusinessProfileService(db_session)
    mine = service.create_profile(business_user.id, BusinessProfileCreate(company_name="Acme SRL"))

    with pytest.raises(NotFoundError):
        service.set_active_profile(other.id, mine.id)


def test_update_profile_leaves_unset_fields_untouched(db_session, business_user):
    service = BusinessProfileService(db_session)
    profile = service.create_profile(business_user.id, BusinessProfileCreate(company_name="Acme SRL", tax_id="RO123"))

    updated = service.update_profile(business_user.id, profile.id, BusinessProfileUpdate(business_category="Retail"))

    assert updated.company_name == "Acme SRL"
    assert updated.tax_id == "RO123"
    assert updated.business_category == "Retail"


def test_statement_uses_active_companys_name_and_representative(db_session, business_user):
    wallet = WalletService(db_session).create_wallet(business_user.id, WalletCreate(currency="RON"))
    service = BusinessProfileService(db_session)
    service.create_profile(
        business_user.id, BusinessProfileCreate(company_name="Acme SRL", representative_name="Ion Pop")
    )
    beta = service.create_profile(business_user.id, BusinessProfileCreate(company_name="Beta SRL"))
    service.set_active_profile(business_user.id, beta.id)

    statement = StatementService(db_session).generate(
        business_user.id,
        StatementRequest(wallet_id=wallet.id, date_from=date.today() - timedelta(days=1), date_to=date.today()),
    )

    assert statement.account_holder_name == "Beta SRL"
    assert statement.representative_name is None  # Beta SRL has no representative set


def test_statement_falls_back_to_personal_name_without_a_profile(db_session, business_user):
    wallet = WalletService(db_session).create_wallet(business_user.id, WalletCreate(currency="RON"))

    statement = StatementService(db_session).generate(
        business_user.id,
        StatementRequest(wallet_id=wallet.id, date_from=date.today() - timedelta(days=1), date_to=date.today()),
    )

    assert statement.account_holder_name == "Biz Owner"


def test_business_profile_endpoints(client, db_session):
    UserService(db_session).create_user(
        UserCreate(
            email="biz-profile-http@example.com",
            phone="+40744444461",
            password="Sup3rSecret!",
            first_name="Http",
            last_name="Biz",
            user_type=UserType.BUSINESS,
        )
    )
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login", json={"email": "biz-profile-http@example.com", "password": "Sup3rSecret!"}
    )
    assert login.status_code == 200
    token = login.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    empty = client.get("/api/v1/business/profile", headers=headers)
    assert empty.status_code == 200
    assert empty.json() is None

    created = client.post("/api/v1/business/profiles", headers=headers, json={"company_name": "HTTP SRL"})
    assert created.status_code == 201
    assert created.json()["company_name"] == "HTTP SRL"
    assert created.json()["is_active"] is True
    profile_id = created.json()["id"]

    second = client.post("/api/v1/business/profiles", headers=headers, json={"company_name": "HTTP Two SRL"})
    assert second.status_code == 201
    assert second.json()["is_active"] is False

    listed = client.get("/api/v1/business/profiles", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    activated = client.put(f"/api/v1/business/profiles/{second.json()['id']}/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True

    active = client.get("/api/v1/business/profile", headers=headers)
    assert active.json()["id"] == second.json()["id"]

    updated = client.put(
        f"/api/v1/business/profiles/{profile_id}", headers=headers, json={"tax_id": "RO999"}
    )
    assert updated.status_code == 200
    assert updated.json()["tax_id"] == "RO999"
    assert updated.json()["company_name"] == "HTTP SRL"


def test_business_profile_endpoint_rejects_personal_user(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "profile-personal@example.com",
            "phone": "+40744444462",
            "password": "Sup3rSecret!",
            "first_name": "Reg",
            "last_name": "Ular",
        },
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": "profile-personal@example.com", "password": "Sup3rSecret!"}
    )
    token = login.json()["tokens"]["access_token"]

    response = client.get("/api/v1/business/profile", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
