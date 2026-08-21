"""SupabaseRestSession has no dedicated tests elsewhere — it's shared
infrastructure every module uses under DATABASE_BACKEND=supabase_rest, but
none of the SQLAlchemy-backed test suite exercises it. These pin flush()'s
dirty-tracking: a row that was only ever fetched (or just added/PATCHed with
no further change) must not get re-PATCHed on the next flush(), which is
what made a handful of real writes in a request balloon into dozens of
redundant HTTP round-trips."""
import uuid
from datetime import datetime, timezone

import pytest

from app.merchants.models import Merchant, MerchantStatus
from app.supabase import SupabaseRestSession


@pytest.fixture()
def session():
    return SupabaseRestSession(url="http://fake.local", key="fake-key")


@pytest.fixture()
def record_requests(monkeypatch, session):
    calls: list[tuple[str, str]] = []

    def fake_request(method, table, **kwargs):
        calls.append((method, table))
        return None

    monkeypatch.setattr(session, "request", fake_request)
    return calls


def _merchant_row(merchant_id: uuid.UUID) -> dict:
    return {
        "id": str(merchant_id),
        "name": "Nike",
        "logo_url": None,
        "category": "Retail",
        "status": "ACTIVE",
        "verified": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_flush_does_not_repatch_a_row_that_was_only_fetched(session, record_requests):
    merchant = session._hydrate(Merchant, _merchant_row(uuid.uuid4()))

    session.flush()

    assert record_requests == []
    assert merchant.name == "Nike"  # unchanged — this is a read, not a fixture check


def test_flush_patches_only_a_row_that_was_actually_mutated(session, record_requests):
    unchanged = session._hydrate(Merchant, _merchant_row(uuid.uuid4()))
    changed = session._hydrate(Merchant, _merchant_row(uuid.uuid4()))
    changed.verified = False

    session.flush()

    assert record_requests == [("PATCH", "merchants")]
    assert unchanged.verified is True


def test_flush_does_not_repeat_a_patch_already_applied(session, record_requests):
    merchant = session._hydrate(Merchant, _merchant_row(uuid.uuid4()))
    merchant.verified = False

    session.flush()
    session.flush()  # e.g. earn_points() and _credit_cashback_to_wallet() both flush per request

    assert record_requests == [("PATCH", "merchants")]


def test_flush_patches_again_after_a_second_real_change(session, record_requests):
    merchant = session._hydrate(Merchant, _merchant_row(uuid.uuid4()))
    merchant.verified = False

    session.flush()
    merchant.category = "Fashion"
    session.flush()

    assert record_requests == [("PATCH", "merchants"), ("PATCH", "merchants")]


def test_add_does_not_get_repatched_by_a_later_unrelated_flush(session, record_requests):
    new_merchant = Merchant(id=uuid.uuid4(), name="Zara", category="Retail", status=MerchantStatus.ACTIVE, verified=True)

    session.add(new_merchant)
    assert record_requests == [("POST", "merchants")]

    session.flush()

    assert record_requests == [("POST", "merchants")]  # still just the one POST, no follow-up PATCH
