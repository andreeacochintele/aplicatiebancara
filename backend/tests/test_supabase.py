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


@pytest.fixture()
def record_bodies(monkeypatch, session):
    calls: list[tuple[str, str, object]] = []

    def fake_request(method, table, *, params=None, body=None, prefer=None):
        calls.append((method, table, body))
        return None

    monkeypatch.setattr(session, "request", fake_request)
    return calls


def test_flush_persists_a_field_explicitly_cleared_to_none(session, record_bodies):
    """Regression test: PATCH must send an explicit null for a field the app
    cleared, not omit it — PostgREST only touches keys present in the body,
    so omitting it silently leaves the old value in place forever."""
    row = _merchant_row(uuid.uuid4())
    row["logo_url"] = "https://example.com/logo.png"
    merchant = session._hydrate(Merchant, row)

    merchant.logo_url = None
    session.flush()

    method, table, body = record_bodies[0]
    assert (method, table) == ("PATCH", "merchants")
    assert body["logo_url"] is None


def test_add_still_omits_an_unset_none_field_from_the_insert_payload(session, record_bodies):
    """INSERT keeps the old omit-when-None behavior on purpose: a brand-new
    row's unset nullable columns should fall through to the DB's own
    server_default, not get pinned to null by the client."""
    new_merchant = Merchant(id=uuid.uuid4(), name="Zara", category="Retail", status=MerchantStatus.ACTIVE, verified=True)

    session.add(new_merchant)

    method, table, body = record_bodies[0]
    assert (method, table) == ("POST", "merchants")
    assert "logo_url" not in body
