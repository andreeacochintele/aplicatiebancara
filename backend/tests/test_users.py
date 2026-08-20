from app.core.exceptions import ConflictError
from app.users.schemas import UserCreate
from app.users.service import UserService

import pytest


def _user_create(**overrides) -> UserCreate:
    data = dict(
        email="jane@example.com",
        phone="+40711111111",
        password="Sup3rSecret!",
        first_name="Jane",
        last_name="Doe",
    )
    data.update(overrides)
    return UserCreate(**data)


def test_create_user(db_session):
    service = UserService(db_session)
    user = service.create_user(_user_create())

    assert user.id is not None
    assert user.email == "jane@example.com"
    assert user.password_hash != "Sup3rSecret!"


def test_create_user_duplicate_email_raises(db_session):
    service = UserService(db_session)
    service.create_user(_user_create())

    with pytest.raises(ConflictError):
        service.create_user(_user_create(phone="+40722222222"))


def test_register_endpoint(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "register@example.com",
            "phone": "+40733333333",
            "password": "Sup3rSecret!",
            "first_name": "Ana",
            "last_name": "Ionescu",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "register@example.com"
    assert "access_token" in body["tokens"]


@pytest.mark.parametrize(
    "weak_password",
    [
        "short1!",  # too short
        "alllowercase1!",  # no uppercase
        "ALLUPPERCASE1!",  # no lowercase
        "NoDigitsHere!",  # no digit
        "NoSpecialChar1",  # no special character
    ],
)
def test_register_endpoint_rejects_weak_password(client, weak_password):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak-password@example.com",
            "phone": "+40733333334",
            "password": weak_password,
            "first_name": "Ana",
            "last_name": "Ionescu",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("invalid_name", ["Ana2", "Ana!", "", "A"])
def test_register_endpoint_rejects_invalid_first_name(client, invalid_name):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-name@example.com",
            "phone": "+40733333335",
            "password": "Sup3rSecret!",
            "first_name": invalid_name,
            "last_name": "Ionescu",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("invalid_phone", ["andrei", "0712345678", "+4071234", "+0712345678", "12345"])
def test_register_endpoint_rejects_invalid_phone(client, invalid_phone):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-phone@example.com",
            "phone": invalid_phone,
            "password": "Sup3rSecret!",
            "first_name": "Ana",
            "last_name": "Ionescu",
        },
    )
    assert response.status_code == 422
