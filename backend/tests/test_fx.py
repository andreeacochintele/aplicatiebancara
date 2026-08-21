from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.fx import service as fx_service_module
from app.fx.models import FXQuoteStatus
from app.fx.schemas import FXQuoteRequest
from app.fx.service import FXService
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture(autouse=True)
def _reset_live_rate_cache():
    """The live-rate cache is process-global; keep each test isolated."""
    fx_service_module._live_rate_cache = None
    fx_service_module._live_rate_cached_at = None
    fx_service_module._history_cache = {}
    yield
    fx_service_module._live_rate_cache = None
    fx_service_module._live_rate_cached_at = None
    fx_service_module._history_cache = {}


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="fx-user@example.com", password="Sup3rSecret!", first_name="Fx", last_name="User")
    )


def test_quote_calculates_target_amount_and_fee(db_session, seeded_user):
    service = FXService(db_session)
    quote = service.get_quote(
        seeded_user.id, FXQuoteRequest(source_currency="EUR", target_currency="RON", source_amount=Decimal("100"))
    )

    assert quote.status == FXQuoteStatus.CREATED
    assert quote.fee == Decimal("0.50")  # 0.5% of 100
    assert quote.exchange_rate == Decimal("4.97")
    assert quote.target_amount == Decimal("494.52")  # (100 - 0.50) * 4.97, rounded


def test_quote_rejects_same_currency(db_session, seeded_user):
    service = FXService(db_session)
    with pytest.raises(ValidationError):
        service.get_quote(
            seeded_user.id, FXQuoteRequest(source_currency="RON", target_currency="RON", source_amount=Decimal("10"))
        )


def test_quote_rejects_unsupported_currency(db_session, seeded_user):
    service = FXService(db_session)
    with pytest.raises(ValidationError):
        service.get_quote(
            seeded_user.id, FXQuoteRequest(source_currency="XXX", target_currency="RON", source_amount=Decimal("10"))
        )


def test_expired_quote_is_rejected(db_session, seeded_user):
    service = FXService(db_session)
    quote = service.get_quote(
        seeded_user.id, FXQuoteRequest(source_currency="EUR", target_currency="RON", source_amount=Decimal("50"))
    )
    quote.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    with pytest.raises(ConflictError):
        service.get_valid_quote_for_user(seeded_user.id, quote.id)

    assert quote.status == FXQuoteStatus.EXPIRED


def test_accepted_quote_cannot_be_reused(db_session, seeded_user):
    service = FXService(db_session)
    quote = service.get_quote(
        seeded_user.id, FXQuoteRequest(source_currency="USD", target_currency="RON", source_amount=Decimal("20"))
    )
    service.mark_accepted(quote)
    db_session.flush()

    with pytest.raises(ConflictError):
        service.get_valid_quote_for_user(seeded_user.id, quote.id)


def test_market_rate_falls_back_to_static_table_when_offline(db_session, monkeypatch):
    monkeypatch.setattr(fx_service_module, "_fetch_live_rates_to_ron", lambda: None)
    service = FXService(db_session)

    rate = service.get_market_rate("EUR", "RON")

    # Static EUR/RON is 4.97; a 1% margin should shave it down a touch.
    assert rate < Decimal("4.97")
    assert rate > Decimal("4.97") * Decimal("0.98")


def test_market_rate_uses_live_rates_with_markup(db_session, monkeypatch):
    monkeypatch.setattr(
        fx_service_module,
        "_fetch_live_rates_to_ron",
        lambda: {"RON": Decimal("1"), "EUR": Decimal("5.00"), "USD": Decimal("4.60")},
    )
    service = FXService(db_session)

    rate = service.get_market_rate("EUR", "RON")

    assert rate == Decimal("4.9500")  # 5.00 * (1 - 1%)


def test_market_rate_same_currency_is_untouched_by_markup(db_session, monkeypatch):
    monkeypatch.setattr(fx_service_module, "_fetch_live_rates_to_ron", lambda: None)
    service = FXService(db_session)

    assert service.get_market_rate("RON", "RON") == Decimal("1")


def test_market_rate_rejects_unsupported_currency(db_session, monkeypatch):
    monkeypatch.setattr(fx_service_module, "_fetch_live_rates_to_ron", lambda: None)
    service = FXService(db_session)

    with pytest.raises(ValidationError):
        service.get_market_rate("XXX", "RON")


def test_rate_history_falls_back_to_a_single_static_point_when_offline(db_session, monkeypatch):
    monkeypatch.setattr(fx_service_module, "_fetch_live_rate_history_to_ron", lambda days: None)
    service = FXService(db_session)

    points = service.get_market_rate_history("EUR", "RON", days=14)

    assert len(points) == 1
    assert points[0].rate < Decimal("4.97")


def test_rate_history_uses_live_daily_rates(db_session, monkeypatch):
    monkeypatch.setattr(
        fx_service_module,
        "_fetch_live_rate_history_to_ron",
        lambda days: {
            "2026-08-18": {"RON": Decimal("1"), "EUR": Decimal("4.95"), "USD": Decimal("4.60")},
            "2026-08-19": {"RON": Decimal("1"), "EUR": Decimal("5.00"), "USD": Decimal("4.65")},
        },
    )
    service = FXService(db_session)

    points = service.get_market_rate_history("EUR", "RON", days=2)

    assert [p.date for p in points] == ["2026-08-18", "2026-08-19"]
    assert points[1].rate == Decimal("4.9500")  # 5.00 * (1 - 1%)


def test_rate_history_rejects_unsupported_currency(db_session, monkeypatch):
    monkeypatch.setattr(fx_service_module, "_fetch_live_rate_history_to_ron", lambda days: None)
    service = FXService(db_session)

    with pytest.raises(ValidationError):
        service.get_market_rate_history("XXX", "RON", days=14)
