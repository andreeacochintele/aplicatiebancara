import pytest

from app.business import anaf_client
from app.core.enums import UserType
from app.core.exceptions import NotFoundError, ValidationError
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_normalize_cui_strips_ro_prefix_and_spaces():
    assert anaf_client.normalize_cui("RO 12345678") == "12345678"
    assert anaf_client.normalize_cui("12345678") == "12345678"


def test_normalize_cui_rejects_bad_length():
    with pytest.raises(ValidationError):
        anaf_client.normalize_cui("1")
    with pytest.raises(ValidationError):
        anaf_client.normalize_cui("12345678901")


def test_lookup_cui_raises_not_found_when_anaf_returns_empty(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"found": [], "notFound": [12345678]}

    monkeypatch.setattr(anaf_client.httpx, "post", lambda *a, **k: FakeResponse())

    with pytest.raises(NotFoundError):
        anaf_client.lookup_cui("12345678")


def test_lookup_cui_parses_found_payload(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "found": [
                    {
                        "date_generale": {
                            "cui": 12345678,
                            "denumire": "ACME SRL",
                            "adresa": "Str. Exemplu nr. 1, Bucuresti",
                            "nrRegCom": "J40/1234/2020",
                            "stare_inactiv": False,
                        }
                    }
                ],
                "notFound": [],
            }

    monkeypatch.setattr(anaf_client.httpx, "post", lambda *a, **k: FakeResponse())

    result = anaf_client.lookup_cui("RO12345678")

    assert result["company_name"] == "ACME SRL"
    assert result["registration_number"] == "J40/1234/2020"
    assert result["is_active"] is True


@pytest.fixture()
def business_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(
            email="biz-cui-lookup@example.com",
            phone="+40744444470",
            password="Sup3rSecret!",
            first_name="Biz",
            last_name="Owner",
            user_type=UserType.BUSINESS,
        )
    )


def test_lookup_cui_endpoint_returns_parsed_result(client, db_session, business_user, monkeypatch):
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login", json={"email": "biz-cui-lookup@example.com", "password": "Sup3rSecret!"}
    )
    token = login.json()["tokens"]["access_token"]

    monkeypatch.setattr(
        anaf_client,
        "lookup_cui",
        lambda cui: {
            "cui": "12345678",
            "company_name": "ACME SRL",
            "registration_number": "J40/1234/2020",
            "address": "Str. Exemplu nr. 1",
            "is_active": True,
        },
    )

    response = client.get(
        "/api/v1/business/lookup-cui/RO12345678", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["company_name"] == "ACME SRL"
    assert response.json()["registration_number"] == "J40/1234/2020"


def test_lookup_cui_endpoint_rejects_personal_user(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "cui-lookup-personal@example.com",
            "phone": "+40744444471",
            "password": "Sup3rSecret!",
            "first_name": "Reg",
            "last_name": "Ular",
        },
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": "cui-lookup-personal@example.com", "password": "Sup3rSecret!"}
    )
    token = login.json()["tokens"]["access_token"]

    response = client.get(
        "/api/v1/business/lookup-cui/12345678", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_lookup_cui_endpoint_returns_404_when_not_found(client, db_session, business_user, monkeypatch):
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login", json={"email": "biz-cui-lookup@example.com", "password": "Sup3rSecret!"}
    )
    token = login.json()["tokens"]["access_token"]

    def raise_not_found(cui):
        raise NotFoundError("CUI-ul nu a fost gasit in registrul ANAF")

    monkeypatch.setattr(anaf_client, "lookup_cui", raise_not_found)

    response = client.get(
        "/api/v1/business/lookup-cui/99999999", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404
