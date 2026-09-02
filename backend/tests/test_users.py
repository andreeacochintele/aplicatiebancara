import uuid

import pytest

from app.auth.models import UserDevice, UserSession
from app.core.enums import UserRole
from app.core.exceptions import ConflictError, NotFoundError
from app.users.schemas import UserCreate
from app.users.service import UserService


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


def test_create_user_concurrent_race_raises_conflict_not_a_bare_500(db_session, monkeypatch):
    """Simulates two requests racing past the pre-check (e.g. two tabs
    registering the same email at once): the DB-level unique constraint is
    what actually stops the second insert, surfacing as an IntegrityError at
    flush() — must become a clean ConflictError, not a bare 500."""
    from sqlalchemy.exc import IntegrityError

    service = UserService(db_session)

    def _boom(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: users.email"))

    monkeypatch.setattr(service.repository, "add", _boom)

    with pytest.raises(ConflictError):
        service.create_user(_user_create())


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


def test_register_endpoint_attaches_a_default_session_device(client, db_session):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "device-register@example.com",
            "phone": "+40733333337",
            "password": "Sup3rSecret!",
            "first_name": "Ana",
            "last_name": "Ionescu",
        },
    )

    assert response.status_code == 201
    user_id = uuid.UUID(response.json()["user"]["id"])
    session = db_session.query(UserSession).filter(UserSession.user_id == user_id).one()
    device = db_session.query(UserDevice).filter(UserDevice.user_id == user_id).one()

    assert session.device_id == device.id
    assert device.device_type == "browser"
    assert device.trusted is False


def test_second_login_promotes_the_default_device_to_trusted(client, db_session):
    """The auto-created device stays untrusted only on its first-ever
    appearance; a later login reusing it means it's not new anymore, or the
    fraud engine's NEW_DEVICE flag would fire on every payment forever."""
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "device-trust@example.com",
            "phone": "+40733333338",
            "password": "Sup3rSecret!",
            "first_name": "Ana",
            "last_name": "Ionescu",
        },
    )
    user_id = uuid.UUID(register.json()["user"]["id"])
    first_device = db_session.query(UserDevice).filter(UserDevice.user_id == user_id).one()
    assert first_device.trusted is False

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "device-trust@example.com", "password": "Sup3rSecret!"},
    )
    assert login.status_code == 200

    db_session.refresh(first_device)
    devices = db_session.query(UserDevice).filter(UserDevice.user_id == user_id).all()
    assert len(devices) == 1  # same placeholder row reused, not a second device
    assert first_device.trusted is True


def test_register_with_referral_code_credits_the_referrer(client):
    referrer = client.post(
        "/api/v1/auth/register",
        json={
            "email": "referrer@example.com",
            "phone": "+40733333334",
            "password": "Sup3rSecret!",
            "first_name": "Refer",
            "last_name": "Rer",
        },
    ).json()
    referrer_token = referrer["tokens"]["access_token"]
    referral_code = client.get(
        "/api/v1/rewards", headers={"Authorization": f"Bearer {referrer_token}"}
    ).json()["referral_code"]

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "referred@example.com",
            "phone": "+40733333335",
            "password": "Sup3rSecret!",
            "first_name": "Referred",
            "last_name": "User",
            "referral_code": referral_code,
        },
    )
    assert response.status_code == 201

    referrer_account = client.get("/api/v1/rewards", headers={"Authorization": f"Bearer {referrer_token}"}).json()
    assert referrer_account["points_balance"] == 500
    assert referrer_account["lifetime_points_earned"] == 500


def test_register_with_invalid_referral_code_is_rejected(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "bad-referral@example.com",
            "phone": "+40733333336",
            "password": "Sup3rSecret!",
            "first_name": "Bad",
            "last_name": "Referral",
            "referral_code": "EASYB-NOTREAL1",
        },
    )
    assert response.status_code == 422

    # No leftover half-registered account -- the same email can still register.
    retry = client.post(
        "/api/v1/auth/register",
        json={
            "email": "bad-referral@example.com",
            "phone": "+40733333336",
            "password": "Sup3rSecret!",
            "first_name": "Bad",
            "last_name": "Referral",
        },
    )
    assert retry.status_code == 201


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


def _login_http(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["tokens"]["access_token"]


def _count_commits(db_session, monkeypatch, make_request):
    calls = []
    monkeypatch.setattr(db_session, "commit", lambda: calls.append(1))
    response = make_request()
    monkeypatch.undo()
    return response, len(calls)


def test_promote_to_admin_sets_role(db_session):
    service = UserService(db_session)
    user = service.create_user(_user_create(email="promote-me@example.com", phone="+40744000001"))
    assert user.role == UserRole.USER

    promoted = service.promote_to_admin("promote-me@example.com")

    assert promoted.id == user.id
    assert promoted.role == UserRole.ADMIN


def test_promote_to_admin_rejects_unknown_email(db_session):
    service = UserService(db_session)

    with pytest.raises(NotFoundError):
        service.promote_to_admin("nobody-here@example.com")


def test_promote_to_admin_rejects_an_existing_admin(db_session):
    service = UserService(db_session)
    service.create_user(_user_create(email="already-admin@example.com", phone="+40744000002"))
    service.promote_to_admin("already-admin@example.com")

    with pytest.raises(ConflictError):
        service.promote_to_admin("already-admin@example.com")


def test_list_admins_returns_only_admin_role_users(db_session):
    service = UserService(db_session)
    service.create_user(_user_create(email="regular-user@example.com", phone="+40744000003"))
    service.create_user(_user_create(email="soon-admin@example.com", phone="+40744000004"))
    service.promote_to_admin("soon-admin@example.com")

    admins = service.list_admins()

    assert {a.email for a in admins} >= {"soon-admin@example.com"}
    assert "regular-user@example.com" not in {a.email for a in admins}


def test_promote_to_admin_endpoint_requires_admin(client, db_session):
    UserService(db_session).create_user(_user_create(email="caller@example.com", phone="+40744000005"))
    db_session.commit()
    token = _login_http(client, "caller@example.com", "Sup3rSecret!")

    response = client.post(
        "/api/v1/users/admin/promote",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "caller@example.com"},
    )

    assert response.status_code == 403


def test_promote_to_admin_endpoint_commits(client, db_session, monkeypatch):
    admin = UserService(db_session).create_user(_user_create(email="promoter-admin@example.com", phone="+40744000006"))
    admin.role = UserRole.ADMIN
    UserService(db_session).create_user(_user_create(email="target-user@example.com", phone="+40744000007"))
    db_session.commit()
    token = _login_http(client, "promoter-admin@example.com", "Sup3rSecret!")
    headers = {"Authorization": f"Bearer {token}"}

    baseline_response, baseline_commits = _count_commits(
        db_session, monkeypatch, lambda: client.get("/api/v1/users/admin/admins", headers=headers)
    )
    assert baseline_response.status_code == 200

    response, commits = _count_commits(
        db_session,
        monkeypatch,
        lambda: client.post("/api/v1/users/admin/promote", headers=headers, json={"email": "target-user@example.com"}),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"
    assert commits > baseline_commits, "POST /users/admin/promote must call db.commit() or the promotion never persists"


def test_list_admins_endpoint_requires_admin(client, db_session):
    UserService(db_session).create_user(_user_create(email="not-an-admin@example.com", phone="+40744000008"))
    db_session.commit()
    token = _login_http(client, "not-an-admin@example.com", "Sup3rSecret!")

    response = client.get("/api/v1/users/admin/admins", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
