"""Shared pytest fixtures. Tests run against an in-memory SQLite database so
the suite needs no Docker/Postgres to run."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.orchestrator import models as ai_orchestrator_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.auth.router import _login_rate_limit, _register_rate_limit
from app.budgets import models as budgets_models  # noqa: F401
from app.cards import models as cards_models  # noqa: F401
from app.credit import models as credit_models  # noqa: F401
from app.database import Base, get_db
from app.exports import models as exports_models  # noqa: F401
from app.fraud import models as fraud_models  # noqa: F401
from app.fx import models as fx_models  # noqa: F401
from app.main import app
from app.merchants import models as merchants_models  # noqa: F401
from app.notifications import models as notifications_models  # noqa: F401
from app.payments import models as payments_models  # noqa: F401
from app.rewards import models as rewards_models  # noqa: F401
from app.savings import models as savings_models  # noqa: F401
from app.transactions import models as transactions_models  # noqa: F401
from app.users import models as users_models  # noqa: F401
from app.wallets import models as wallets_models  # noqa: F401


@pytest.fixture(autouse=True)
def _no_live_fx_rates_by_default(monkeypatch):
    """FXService.get_quote() now prices off the same live-rate-with-fallback
    path as the Wallets display rate (get_market_rate) — previously it used
    the static _RATES_TO_RON table unconditionally. Any test that creates an
    FX quote (directly, or indirectly via a cross-currency transfer/wallet
    close/savings contribution) would otherwise depend on real network
    access. Mocked to "network unavailable" here so the whole suite falls
    back to the static table by default, matching every hardcoded expected
    value; tests that want to exercise the real live-rate path override this
    themselves (see test_fx.py)."""
    from app.fx import service as fx_service_module

    monkeypatch.setattr(fx_service_module, "_fetch_live_rates_to_ron", lambda: None)
    monkeypatch.setattr(fx_service_module, "_fetch_live_rate_history_to_ron", lambda days: None)
    fx_service_module._live_rate_cache = None
    fx_service_module._live_rate_cached_at = None
    fx_service_module._history_cache = {}


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # The suite registers/logs in far more than the real per-IP rate limits
    # allow (every TestClient request shares one simulated client IP) — off
    # by default here so that doesn't trip; tests/test_rate_limit.py exercises
    # the real limiting behavior with its own TestClient, override cleared.
    app.dependency_overrides[_login_rate_limit] = lambda: None
    app.dependency_overrides[_register_rate_limit] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
