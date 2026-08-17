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
