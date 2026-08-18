from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.fx.models import FXQuoteStatus
from app.fx.schemas import FXQuoteRequest
from app.fx.service import FXService
from app.users.schemas import UserCreate
from app.users.service import UserService


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
            seeded_user.id, FXQuoteRequest(source_currency="JPY", target_currency="RON", source_amount=Decimal("10"))
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
