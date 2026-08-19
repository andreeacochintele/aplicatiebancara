"""Shared pytest fixtures. Tests run against an in-memory SQLite database so
the suite needs no Docker/Postgres to run."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import models as auth_models  # noqa: F401
from app.budgets import models as budgets_models  # noqa: F401
from app.cards import models as cards_models  # noqa: F401
from app.credit import models as credit_models  # noqa: F401
from app.database import Base, get_db
from app.fx import models as fx_models  # noqa: F401
from app.main import app
from app.merchants import models as merchants_models  # noqa: F401
from app.payments import models as payments_models  # noqa: F401
from app.rewards.models import RewardTier
from app.savings import models as savings_models  # noqa: F401
from app.transactions import models as transactions_models  # noqa: F401
from app.users import models as users_models  # noqa: F401
from app.wallets import models as wallets_models  # noqa: F401


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


@pytest.fixture(autouse=True)
def seeded_reward_tiers(db_session):
    """Mirrors migration 0005's reference-data seed (STANDARD/PREMIUM/METAL) —
    tests run against Base.metadata.create_all(), not the migrations, so
    reward tier rows (every account needs at least one to resolve a tier)
    need seeding here instead."""
    tiers = {
        "STANDARD": RewardTier(name="STANDARD", min_lifetime_points=0, perks="Earn 1 point per RON spent", sort_order=0),
        "PREMIUM": RewardTier(
            name="PREMIUM", min_lifetime_points=2000, perks="Airport lounge access|Priority support", sort_order=1
        ),
        "METAL": RewardTier(
            name="METAL", min_lifetime_points=8000, perks="Unlimited lounge access|Concierge support", sort_order=2
        ),
    }
    db_session.add_all(tiers.values())
    db_session.flush()
    return tiers


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
