import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.auth.models import SessionStatus, UserSession
from app.config import get_settings

settings = get_settings()


def _register(client, email: str = "auth-user@example.com", phone: str = "+40711111111") -> str:
    return _register_tokens(client, email, phone)["access_token"]


def _register_tokens(client, email: str = "auth-user@example.com", phone: str = "+40711111111") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": phone,
            "password": "Sup3rSecret!",
            "first_name": "Auth",
            "last_name": "User",
        },
    )
    assert response.status_code == 201
    return response.json()["tokens"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _only_session(db_session) -> UserSession:
    return db_session.scalars(select(UserSession)).one()


def test_register_issues_a_usable_access_token(client):
    token = _register(client)

    response = client.get("/api/v1/users/me", headers=_headers(token))

    assert response.status_code == 200


def test_login_issues_a_usable_access_token(client):
    _register(client, "auth-login@example.com", "+40711111112")

    login = client.post(
        "/api/v1/auth/login", json={"email": "auth-login@example.com", "password": "Sup3rSecret!"}
    )
    assert login.status_code == 200
    token = login.json()["tokens"]["access_token"]

    response = client.get("/api/v1/users/me", headers=_headers(token))

    assert response.status_code == 200


def test_authenticated_request_bumps_last_activity_at(client, db_session):
    token = _register(client, "auth-activity@example.com", "+40711111113")
    session = _only_session(db_session)
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    db_session.commit()
    stale_activity = session.last_activity_at

    response = client.get("/api/v1/users/me", headers=_headers(token))

    assert response.status_code == 200
    db_session.expire(session)
    assert session.last_activity_at > stale_activity


def test_request_after_idle_timeout_is_rejected_and_expires_the_session(client, db_session):
    token = _register(client, "auth-idle@example.com", "+40711111114")
    session = _only_session(db_session)
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES + 1
    )
    db_session.commit()

    response = client.get("/api/v1/users/me", headers=_headers(token))

    assert response.status_code == 401
    db_session.expire(session)
    assert session.status == SessionStatus.EXPIRED


def test_request_after_absolute_expiry_is_rejected(client, db_session):
    token = _register(client, "auth-absolute-expiry@example.com", "+40711111115")
    session = _only_session(db_session)
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    response = client.get("/api/v1/users/me", headers=_headers(token))

    assert response.status_code == 401
    db_session.expire(session)
    assert session.status == SessionStatus.EXPIRED


def test_logout_revokes_the_session(client, db_session):
    token = _register(client, "auth-logout@example.com", "+40711111116")

    logout = client.post("/api/v1/auth/logout", headers=_headers(token))

    assert logout.status_code == 204
    session = _only_session(db_session)
    assert session.status == SessionStatus.REVOKED


def test_request_after_logout_is_rejected(client):
    token = _register(client, "auth-logout-reject@example.com", "+40711111117")
    client.post("/api/v1/auth/logout", headers=_headers(token))

    response = client.get("/api/v1/users/me", headers=_headers(token))

    assert response.status_code == 401


def test_logout_others_revokes_other_sessions_but_keeps_the_current_one(client, db_session):
    first_token = _register(client, "auth-logout-others@example.com", "+40711111119")
    second_login = client.post(
        "/api/v1/auth/login", json={"email": "auth-logout-others@example.com", "password": "Sup3rSecret!"}
    )
    second_token = second_login.json()["tokens"]["access_token"]

    response = client.post("/api/v1/auth/logout-others", headers=_headers(second_token))

    assert response.status_code == 200
    assert response.json()["revoked_sessions"] == 1

    # The session behind first_token is now revoked...
    stale = client.get("/api/v1/users/me", headers=_headers(first_token))
    assert stale.status_code == 401
    # ...but the one that made the logout-others call still works.
    current = client.get("/api/v1/users/me", headers=_headers(second_token))
    assert current.status_code == 200

    sessions = db_session.scalars(select(UserSession)).all()
    statuses = {s.status for s in sessions}
    assert SessionStatus.REVOKED in statuses
    assert SessionStatus.ACTIVE in statuses


def test_token_without_a_sid_claim_is_rejected(client):
    now = datetime.now(timezone.utc)
    legacy_payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "jti": str(uuid.uuid4()),
    }
    legacy_token = jwt.encode(legacy_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    response = client.get("/api/v1/users/me", headers=_headers(legacy_token))

    assert response.status_code == 401


def test_refresh_issues_a_new_usable_access_token(client):
    tokens = _register_tokens(client, "auth-refresh@example.com", "+40711111119")

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert refresh.status_code == 200
    new_access_token = refresh.json()["access_token"]
    assert new_access_token != tokens["access_token"]
    response = client.get("/api/v1/users/me", headers=_headers(new_access_token))
    assert response.status_code == 200


def test_refresh_does_not_bump_last_activity_at(client, db_session):
    tokens = _register_tokens(client, "auth-refresh-idle@example.com", "+40711111120")
    session = _only_session(db_session)
    stale_activity = datetime.now(timezone.utc) - timedelta(minutes=2)
    session.last_activity_at = stale_activity
    db_session.commit()

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert refresh.status_code == 200
    db_session.expire(session)
    assert session.last_activity_at.replace(tzinfo=timezone.utc) == stale_activity


def test_refresh_after_idle_timeout_is_rejected_and_expires_the_session(client, db_session):
    tokens = _register_tokens(client, "auth-refresh-idle-expired@example.com", "+40711111121")
    session = _only_session(db_session)
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES + 1
    )
    db_session.commit()

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert refresh.status_code == 401
    db_session.expire(session)
    assert session.status == SessionStatus.EXPIRED


def test_refresh_after_absolute_expiry_is_rejected(client, db_session):
    tokens = _register_tokens(client, "auth-refresh-absolute-expiry@example.com", "+40711111122")
    session = _only_session(db_session)
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert refresh.status_code == 401


def test_refresh_after_logout_is_rejected(client):
    tokens = _register_tokens(client, "auth-refresh-logout@example.com", "+40711111123")
    client.post("/api/v1/auth/logout", headers=_headers(tokens["access_token"]))

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert refresh.status_code == 401


def test_refresh_with_an_access_token_is_rejected(client):
    tokens = _register_tokens(client, "auth-refresh-wrong-type@example.com", "+40711111124")

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})

    assert refresh.status_code == 401


def test_token_with_an_unknown_session_id_is_rejected(client):
    token = _register(client, "auth-unknown-session@example.com", "+40711111118")
    now = datetime.now(timezone.utc)
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    payload["sid"] = str(uuid.uuid4())
    payload["iat"], payload["exp"] = now, now + timedelta(minutes=15)
    forged_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    response = client.get("/api/v1/users/me", headers=_headers(forged_token))

    assert response.status_code == 401
