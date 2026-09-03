from decimal import Decimal
from uuid import UUID

from app.payments.models import ScheduledPaymentFrequency, ScheduledPaymentStatus
from app.transactions.models import TransactionStatus
from app.wallets.models import Wallet
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


def _register(client, email: str, phone: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": phone,
            "password": "Sup3rSecret!",
            "first_name": email.split("@")[0].title(),
            "last_name": "User",
        },
    )
    assert response.status_code == 201
    return response.json()


def _auth_header(auth_response: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_response['tokens']['access_token']}"}


def _create_wallet(db_session, user_id: str, currency: str, balance: Decimal = Decimal("0")) -> Wallet:
    wallet = WalletService(db_session).create_wallet(UUID(user_id), WalletCreate(currency=currency))
    wallet.available_balance = balance
    db_session.flush()
    return wallet


def _payload(wallet: Wallet, **overrides) -> dict:
    payload = {
        "name": "Salarii lunare",
        "source_wallet_id": str(wallet.id),
        "currency": wallet.currency,
        "frequency": ScheduledPaymentFrequency.MONTHLY,
        "next_run_on": "2026-01-31",
        "rows": [
            {"beneficiary_name": "Ana Ionescu", "iban": "RO49AAAA1B31007593840001", "amount": "1000.00"},
            {"beneficiary_name": "Bogdan Radu", "iban": "RO49AAAA1B31007593840002", "amount": "500.00"},
        ],
    }
    payload.update(overrides)
    return payload


def test_create_bulk_transfer_template(client, db_session):
    owner = _register(client, "template-owner@example.com", "+40751100001")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))

    response = client.post(
        "/api/v1/payments/transfers/bulk/templates",
        headers=_auth_header(owner),
        json=_payload(wallet),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Salarii lunare"
    assert body["status"] == ScheduledPaymentStatus.ACTIVE
    assert body["next_run_on"] == "2026-01-31"
    assert len(body["rows"]) == 2
    assert body["rows"][0]["beneficiary_name"] == "Ana Ionescu"


def test_update_template_replaces_name_frequency_and_rows(client, db_session):
    owner = _register(client, "template-editor@example.com", "+40751100010")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates",
        headers=_auth_header(owner),
        json=_payload(wallet),
    ).json()

    response = client.put(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}",
        headers=_auth_header(owner),
        json={
            "name": "Salarii lunare - actualizat",
            "frequency": ScheduledPaymentFrequency.WEEKLY,
            "next_run_on": "2026-02-07",
            "rows": [
                {"beneficiary_name": "Costel Enache", "iban": "RO49AAAA1B31007593840003", "amount": "750.00"},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Salarii lunare - actualizat"
    assert body["frequency"] == ScheduledPaymentFrequency.WEEKLY
    assert body["next_run_on"] == "2026-02-07"
    assert len(body["rows"]) == 1
    assert body["rows"][0]["beneficiary_name"] == "Costel Enache"


def test_update_template_without_rows_keeps_existing_rows(client, db_session):
    owner = _register(client, "template-editor-partial@example.com", "+40751100011")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates",
        headers=_auth_header(owner),
        json=_payload(wallet),
    ).json()

    response = client.put(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}",
        headers=_auth_header(owner),
        json={"name": "Doar numele s-a schimbat"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Doar numele s-a schimbat"
    assert len(body["rows"]) == 2


def test_update_template_rejects_another_owners_template(client, db_session):
    owner = _register(client, "template-owner-locked@example.com", "+40751100012")
    other = _register(client, "template-owner-other@example.com", "+40751100013")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates",
        headers=_auth_header(owner),
        json=_payload(wallet),
    ).json()

    response = client.put(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}",
        headers=_auth_header(other),
        json={"name": "Nu ar trebui sa mearga"},
    )

    assert response.status_code == 404


def test_create_template_rejects_currency_mismatch(client, db_session):
    owner = _register(client, "template-mismatch@example.com", "+40751100002")
    wallet = _create_wallet(db_session, owner["user"]["id"], "EUR", Decimal("5000.00"))

    response = client.post(
        "/api/v1/payments/transfers/bulk/templates",
        headers=_auth_header(owner),
        json=_payload(wallet, currency="RON"),
    )

    assert response.status_code == 422


def test_list_templates_returns_only_owners_own(client, db_session):
    owner = _register(client, "template-list-owner@example.com", "+40751100003")
    other = _register(client, "template-list-other@example.com", "+40751100004")
    owner_wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    other_wallet = _create_wallet(db_session, other["user"]["id"], "RON", Decimal("5000.00"))

    client.post(
        "/api/v1/payments/transfers/bulk/templates", headers=_auth_header(owner), json=_payload(owner_wallet)
    )
    client.post(
        "/api/v1/payments/transfers/bulk/templates", headers=_auth_header(other), json=_payload(other_wallet)
    )

    response = client.get("/api/v1/payments/transfers/bulk/templates", headers=_auth_header(owner))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["owner_user_id"] == owner["user"]["id"]


def test_run_now_executes_rows_and_advances_next_run_on_with_month_end_clamping(client, db_session):
    owner = _register(client, "template-run@example.com", "+40751100005")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates",
        headers=_auth_header(owner),
        json=_payload(wallet, next_run_on="2026-01-31"),
    ).json()

    response = client.post(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}/run", headers=_auth_header(owner)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert all(row["status"] == TransactionStatus.COMPLETED for row in body["results"])

    db_session.refresh(wallet)
    assert wallet.available_balance == Decimal("3500.00")

    templates = client.get("/api/v1/payments/transfers/bulk/templates", headers=_auth_header(owner)).json()
    template = next(t for t in templates if t["id"] == created["id"])
    # January 31 + 1 month clamps to February 28 (2026 is not a leap year) —
    # same day-of-month clamping as the frontend calendar's own projection.
    assert template["next_run_on"] == "2026-02-28"
    assert template["status"] == ScheduledPaymentStatus.ACTIVE


def test_run_now_for_a_once_template_cancels_it_instead_of_advancing(client, db_session):
    owner = _register(client, "template-once@example.com", "+40751100006")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates",
        headers=_auth_header(owner),
        json=_payload(wallet, frequency=ScheduledPaymentFrequency.ONCE),
    ).json()

    client.post(f"/api/v1/payments/transfers/bulk/templates/{created['id']}/run", headers=_auth_header(owner))

    templates = client.get("/api/v1/payments/transfers/bulk/templates", headers=_auth_header(owner)).json()
    template = next(t for t in templates if t["id"] == created["id"])
    assert template["status"] == ScheduledPaymentStatus.CANCELLED


def test_run_now_rejects_a_paused_template(client, db_session):
    owner = _register(client, "template-paused@example.com", "+40751100007")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates", headers=_auth_header(owner), json=_payload(wallet)
    ).json()
    client.patch(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}/status",
        headers=_auth_header(owner),
        json={"status": ScheduledPaymentStatus.PAUSED},
    )

    response = client.post(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}/run", headers=_auth_header(owner)
    )

    assert response.status_code == 409


def test_update_status_pause_then_resume(client, db_session):
    owner = _register(client, "template-status@example.com", "+40751100008")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates", headers=_auth_header(owner), json=_payload(wallet)
    ).json()

    paused = client.patch(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}/status",
        headers=_auth_header(owner),
        json={"status": ScheduledPaymentStatus.PAUSED},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == ScheduledPaymentStatus.PAUSED

    resumed = client.patch(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}/status",
        headers=_auth_header(owner),
        json={"status": ScheduledPaymentStatus.ACTIVE},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == ScheduledPaymentStatus.ACTIVE


def test_update_status_rejects_reactivating_a_cancelled_template(client, db_session):
    owner = _register(client, "template-cancelled@example.com", "+40751100009")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("5000.00"))
    created = client.post(
        "/api/v1/payments/transfers/bulk/templates", headers=_auth_header(owner), json=_payload(wallet)
    ).json()
    client.patch(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}/status",
        headers=_auth_header(owner),
        json={"status": ScheduledPaymentStatus.CANCELLED},
    )

    response = client.patch(
        f"/api/v1/payments/transfers/bulk/templates/{created['id']}/status",
        headers=_auth_header(owner),
        json={"status": ScheduledPaymentStatus.ACTIVE},
    )

    assert response.status_code == 409
