"""Exercises the real login/register rate limits — every other test file
gets these overridden to a no-op via the shared `client` fixture (see
conftest.py), so this file builds its own TestClient without that override."""
import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import reset_rate_limits
from app.database import Base, get_db
from app.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def raw_client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    reset_rate_limits()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    reset_rate_limits()
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _register_payload(email: str) -> dict:
    return {
        "email": email,
        "phone": f"+4071{hash(email) % 10000000:07d}",
        "password": "Sup3rSecret!",
        "first_name": "Rate",
        "last_name": "Limit",
    }


def test_login_is_rate_limited_after_repeated_attempts(raw_client):
    raw_client.post("/api/v1/auth/register", json=_register_payload("rate-limit-login@example.com"))

    responses = [
        raw_client.post(
            "/api/v1/auth/login", json={"email": "rate-limit-login@example.com", "password": "wrong-password"}
        )
        for _ in range(11)
    ]

    assert [r.status_code for r in responses[:10]] == [401] * 10
    assert responses[10].status_code == 429


def test_register_is_rate_limited_after_repeated_attempts(raw_client):
    responses = [
        raw_client.post("/api/v1/auth/register", json=_register_payload(f"rate-limit-register-{i}@example.com"))
        for i in range(6)
    ]

    assert [r.status_code for r in responses[:5]] == [201] * 5
    assert responses[5].status_code == 429


def test_rate_limit_is_scoped_per_endpoint(raw_client):
    """Hitting the register limit must not also block login for the same
    client — they're independent counters."""
    for i in range(5):
        raw_client.post("/api/v1/auth/register", json=_register_payload(f"rate-limit-scope-{i}@example.com"))
    blocked = raw_client.post(
        "/api/v1/auth/register", json=_register_payload("rate-limit-scope-blocked@example.com")
    )
    assert blocked.status_code == 429

    login_response = raw_client.post(
        "/api/v1/auth/login", json={"email": "rate-limit-scope-0@example.com", "password": "Sup3rSecret!"}
    )
    assert login_response.status_code == 200
