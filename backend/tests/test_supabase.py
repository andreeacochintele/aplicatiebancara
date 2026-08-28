"""SupabaseRestSession has no dedicated tests elsewhere — it's shared
infrastructure every module uses under DATABASE_BACKEND=supabase_rest, but
none of the SQLAlchemy-backed test suite exercises it. These pin flush()'s
dirty-tracking: a row that was only ever fetched (or just added/PATCHed with
no further change) must not get re-PATCHed on the next flush(), which is
what made a handful of real writes in a request balloon into dozens of
redundant HTTP round-trips."""
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

import pytest

import app.supabase as supabase_module
from app.credit.models import CreditDocument, CreditDocumentPurpose, CreditDocumentStatus, LoanInstallment, LoanPayment, LoanPaymentType
import app.credit.repository as credit_repository_module
from app.credit.repository import CreditRepository
from app.merchants.models import Merchant, MerchantStatus
from app.fraud.models import FraudCase
from app.fraud.repository import FraudRepository
from app.supabase import SupabaseRestSession
from app.wallets.models import Wallet


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
    new_merchant = Merchant(
        id=uuid.uuid4(),
        name="Zara",
        category="Retail",
        status=MerchantStatus.ACTIVE,
        verified=True,
    )

    session.add(new_merchant)
    assert record_requests == [("POST", "merchants")]

    session.flush()

    assert record_requests == [("POST", "merchants")]  # still just the one POST, no follow-up PATCH


def test_fetching_an_added_row_reuses_the_tracked_instance(session, record_bodies):
    """Regression test for write-then-read flows such as card payments.

    A transaction is inserted, fraud scoring reads recent transactions, and
    then the original transaction is marked COMPLETED/PENDING_REVIEW. The
    read must not replace the tracked object, or flush() loses the later
    status update.
    """
    merchant_id = uuid.uuid4()
    new_merchant = Merchant(
        id=merchant_id,
        name="Cinema City",
        category="Entertainment",
        status=MerchantStatus.ACTIVE,
    )

    session.add(new_merchant)
    fetched = session._hydrate(Merchant, _merchant_row(merchant_id))

    assert fetched is new_merchant

    new_merchant.verified = True
    session.flush()

    method, table, body = record_bodies[-1]
    assert (method, table) == ("PATCH", "merchants")
    assert body["verified"] is True


def test_fetch_many_does_not_track_a_row_fetched_with_a_narrow_select(session, record_bodies):
    """Regression test: TransactionRepository.list_for_user (and
    get_for_user) fetch wallets with select=id only, to build an id filter
    set — they never intend to write those wallets back. A prior bug
    tracked that partial object into flush()'s identity map anyway, so the
    next unrelated flush() in the same request PATCHed the wallet with
    every other column nulled out, tripping wallets.user_id's NOT NULL
    constraint (reproduced via a card payment: fraud scoring's
    list_for_user call touched every one of the payer's other wallets this
    way)."""
    wallet_id = uuid.uuid4()
    # Simulate the id-only row PostgREST returns for `select=id`.
    hydrated = session._hydrate(Wallet, {"id": str(wallet_id)})

    assert hydrated.id == wallet_id
    assert hydrated.user_id is None

    session.flush()

    assert record_bodies == []


def test_fetch_many_skips_a_row_with_a_value_unknown_to_the_current_schema(monkeypatch, session):
    """Regression test: one row written by a value the running code's enums
    don't recognize (legacy data, or a column shared with an unmerged
    branch) must not 500 every other row in the same list for every other
    caller -- it should be skipped, not fatal to the batch."""
    good_row = _merchant_row(uuid.uuid4())
    bad_row = _merchant_row(uuid.uuid4())
    bad_row["status"] = "NOT_A_REAL_STATUS"

    monkeypatch.setattr(session, "request", lambda method, table, **kwargs: [bad_row, good_row])

    results = session.fetch_many(Merchant, {})

    assert [str(m.id) for m in results] == [good_row["id"]]


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


def test_flush_retries_patch_without_a_column_missing_from_supabase_schema(session, monkeypatch):
    merchant = session._hydrate(Merchant, _merchant_row(uuid.uuid4()))
    merchant.verified = False
    merchant.logo_url = "https://example.com/logo.png"
    calls: list[dict[str, object]] = []

    def fake_request(method, table, *, params=None, body=None, prefer=None):
        calls.append({"method": method, "table": table, "body": dict(body or {})})
        if len(calls) == 1:
            raise RuntimeError(
                "Supabase REST request failed with HTTP 400: "
                '{"message":"Could not find the \'logo_url\' column of \'merchants\' in the schema cache"}'
            )
        return None

    monkeypatch.setattr(session, "request", fake_request)

    session.flush()

    assert len(calls) == 2
    assert calls[0]["body"]["logo_url"] == "https://example.com/logo.png"
    assert "logo_url" not in calls[1]["body"]
    assert calls[1]["body"]["verified"] is False


def test_add_retries_insert_without_a_column_missing_from_supabase_schema(session, monkeypatch):
    new_merchant = Merchant(
        id=uuid.uuid4(),
        name="Zara",
        logo_url="https://example.com/logo.png",
        category="Retail",
        status=MerchantStatus.ACTIVE,
        verified=True,
    )
    calls: list[dict[str, object]] = []

    def fake_request(method, table, *, params=None, body=None, prefer=None):
        calls.append({"method": method, "table": table, "body": dict(body or {})})
        if len(calls) == 1:
            raise RuntimeError(
                "Supabase REST request failed with HTTP 400: "
                '{"message":"Could not find the \'logo_url\' column of \'merchants\' in the schema cache"}'
            )
        return None

    monkeypatch.setattr(session, "request", fake_request)

    session.add(new_merchant)

    assert len(calls) == 2
    assert calls[0]["body"]["logo_url"] == "https://example.com/logo.png"
    assert "logo_url" not in calls[1]["body"]
    assert calls[1]["body"]["name"] == "Zara"


def test_fraud_repository_treats_missing_supabase_fraud_table_as_empty(session, monkeypatch):
    def fake_fetch_many(model, params):
        assert model is FraudCase
        raise RuntimeError(
            "Supabase REST request failed with HTTP 404: "
            '{"message":"Could not find the table \'public.fraud_cases\' in the schema cache"}'
        )

    monkeypatch.setattr(session, "fetch_many", fake_fetch_many)

    assert FraudRepository(session).list_pending() == []


def test_credit_document_upload_falls_back_when_supabase_document_columns_are_missing(session, monkeypatch):
    user_id = uuid.uuid4()
    application_id = uuid.uuid4()
    document_id = uuid.uuid4()
    store_path = Path("backend/.credit_documents_test.json")
    if store_path.exists():
        store_path.unlink()
    monkeypatch.setattr(credit_repository_module, "_DOCUMENT_STORE_PATH", store_path)

    def fake_request(method, table, *, params=None, body=None, prefer=None):
        if method == "GET" and table == "credit_documents":
            raise RuntimeError(
                "Supabase REST request failed with HTTP 400: "
                '{"message":"column credit_documents.application_id does not exist"}'
            )
        return None

    monkeypatch.setattr(session, "request", fake_request)
    repository = CreditRepository(session)

    repository.add_document(
        CreditDocument(
            id=document_id,
            user_id=user_id,
            application_id=application_id,
            purpose=CreditDocumentPurpose.LOAN_APPLICATION,
            document_type="Mortgage documentation",
            file_name="salary.pdf",
            content_type="application/pdf",
            file_size=10,
            content_base64="c2FsYXJ5LXBkZg==",
            status=CreditDocumentStatus.UPLOADED,
        )
    )

    documents = repository.list_documents()

    assert documents[0].id == document_id
    assert documents[0].application_id == application_id
    assert documents[0].content_base64 == "c2FsYXJ5LXBkZg=="
    store_path.unlink(missing_ok=True)


def test_credit_repository_skips_installment_persistence_when_supabase_table_is_missing(session, monkeypatch):
    loan_id = uuid.uuid4()

    def fake_add(model):
        assert isinstance(model, LoanInstallment)
        raise RuntimeError(
            "Supabase REST request failed with HTTP 404: "
            '{"message":"Could not find the table \'public.loan_installments\' in the schema cache"}'
        )

    monkeypatch.setattr(session, "add", fake_add)

    installments = [
        LoanInstallment(
            loan_id=loan_id,
            installment_number=1,
            due_date=datetime.now(timezone.utc).date(),
            payment_amount=100,
            principal_amount=90,
            interest_amount=10,
            remaining_principal=0,
        )
    ]

    assert CreditRepository(session).add_installments(installments) == installments


# ---- transient-network-failure resilience fix: a flaky hop to Supabase
# (confirmed live — the same request ranging from <1s to a full 35s hang in
# the same minute) used to burn the full 30s timeout on the first bad
# attempt with no retry. request() -> _send_with_retries() now uses a
# shorter per-attempt timeout and retries a couple of times on a transient
# failure, but never on a real HTTPError (a genuine server answer).


class _FakeUrlopenResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeUrlopenResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr(supabase_module.time, "sleep", lambda seconds: None)


def test_request_retries_a_transient_timeout_then_succeeds(session, monkeypatch, no_sleep):
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] < 2:
            raise TimeoutError("simulated transient timeout")
        return _FakeUrlopenResponse(b'[{"id": "abc"}]')

    monkeypatch.setattr(supabase_module, "urlopen", fake_urlopen)

    result = session.request("GET", "merchants")

    assert calls["count"] == 2
    assert result == [{"id": "abc"}]


def test_request_gives_up_after_max_attempts_on_a_persistent_timeout(session, monkeypatch, no_sleep):
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        raise TimeoutError("simulated persistent timeout")

    monkeypatch.setattr(supabase_module, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="failed after"):
        session.request("GET", "merchants")

    assert calls["count"] == supabase_module._MAX_ATTEMPTS


def test_request_does_not_retry_a_real_http_error(session, monkeypatch, no_sleep):
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"message": "bad request"}'))

    monkeypatch.setattr(supabase_module, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTP 400"):
        session.request("GET", "merchants")

    assert calls["count"] == 1  # not retried — a real server answer, not a network blip


def test_credit_repository_skips_loan_payment_persistence_when_supabase_table_is_missing(session, monkeypatch):
    payment = LoanPayment(
        loan_id=uuid.uuid4(),
        amount=100,
        principal_paid=100,
        interest_paid=0,
        payment_type=LoanPaymentType.EARLY_REPAYMENT,
    )

    def fake_add(model):
        assert isinstance(model, LoanPayment)
        raise RuntimeError(
            "Supabase REST request failed with HTTP 404: "
            '{"message":"Could not find the table \'public.loan_payments\' in the schema cache"}'
        )

    monkeypatch.setattr(session, "add", fake_add)

    assert CreditRepository(session).add_loan_payment(payment) is payment
