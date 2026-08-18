from decimal import Decimal
from uuid import UUID

from app.payments.models import ScheduledPaymentFrequency, ScheduledPaymentStatus
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


def _payload(wallet: Wallet) -> dict:
    return {
        "beneficiary_name": "Enel Energie",
        "iban": "RO88CCCC1B31007593841023",
        "source_wallet_id": str(wallet.id),
        "amount": "750.00",
        "currency": wallet.currency,
        "frequency": ScheduledPaymentFrequency.MONTHLY,
        "next_run_on": "2026-09-25",
        "notify_days_before": 3,
        "description": "Electricity bill",
    }


def test_create_and_list_scheduled_payments(client, db_session):
    auth = _register(client, "scheduled-owner@example.com", "+40760111111")
    wallet = _create_wallet(db_session, auth["user"]["id"], "RON", Decimal("1000.00"))

    create_response = client.post(
        "/api/v1/payments/scheduled-payments",
        headers=_auth_header(auth),
        json=_payload(wallet),
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["owner_user_id"] == auth["user"]["id"]
    assert created["beneficiary_name"] == "Enel Energie"
    assert created["amount"] == "750.00"
    assert created["status"] == ScheduledPaymentStatus.ACTIVE

    list_response = client.get("/api/v1/payments/scheduled-payments", headers=_auth_header(auth))
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]


def test_scheduled_payments_are_scoped_to_owner(client, db_session):
    owner = _register(client, "scheduled-private@example.com", "+40760222222")
    other = _register(client, "scheduled-other@example.com", "+40760333333")
    wallet = _create_wallet(db_session, owner["user"]["id"], "RON")
    created = client.post(
        "/api/v1/payments/scheduled-payments",
        headers=_auth_header(owner),
        json=_payload(wallet),
    ).json()

    other_list = client.get("/api/v1/payments/scheduled-payments", headers=_auth_header(other))
    assert other_list.status_code == 200
    assert other_list.json() == []

    other_get = client.get(
        f"/api/v1/payments/scheduled-payments/{created['id']}",
        headers=_auth_header(other),
    )
    assert other_get.status_code == 404


def test_update_scheduled_payment_and_status_transitions(client, db_session):
    auth = _register(client, "scheduled-update@example.com", "+40760444444")
    wallet = _create_wallet(db_session, auth["user"]["id"], "RON")
    created = client.post(
        "/api/v1/payments/scheduled-payments",
        headers=_auth_header(auth),
        json=_payload(wallet),
    ).json()

    pause_response = client.patch(
        f"/api/v1/payments/scheduled-payments/{created['id']}",
        headers=_auth_header(auth),
        json={"status": ScheduledPaymentStatus.PAUSED, "amount": "800.00"},
    )
    assert pause_response.status_code == 200
    paused = pause_response.json()
    assert paused["status"] == ScheduledPaymentStatus.PAUSED
    assert paused["amount"] == "800.00"

    resume_response = client.patch(
        f"/api/v1/payments/scheduled-payments/{created['id']}",
        headers=_auth_header(auth),
        json={"status": ScheduledPaymentStatus.ACTIVE},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == ScheduledPaymentStatus.ACTIVE


def test_cancelled_scheduled_payment_cannot_be_reactivated(client, db_session):
    auth = _register(client, "scheduled-cancel@example.com", "+40760555555")
    wallet = _create_wallet(db_session, auth["user"]["id"], "RON")
    created = client.post(
        "/api/v1/payments/scheduled-payments",
        headers=_auth_header(auth),
        json=_payload(wallet),
    ).json()

    cancel_response = client.patch(
        f"/api/v1/payments/scheduled-payments/{created['id']}",
        headers=_auth_header(auth),
        json={"status": ScheduledPaymentStatus.CANCELLED},
    )
    assert cancel_response.status_code == 200

    reactivate_response = client.patch(
        f"/api/v1/payments/scheduled-payments/{created['id']}",
        headers=_auth_header(auth),
        json={"status": ScheduledPaymentStatus.ACTIVE},
    )
    assert reactivate_response.status_code == 409


def test_scheduled_payment_rejects_currency_mismatch(client, db_session):
    auth = _register(client, "scheduled-currency@example.com", "+40760666666")
    wallet = _create_wallet(db_session, auth["user"]["id"], "RON")
    payload = _payload(wallet)
    payload["currency"] = "EUR"

    response = client.post(
        "/api/v1/payments/scheduled-payments",
        headers=_auth_header(auth),
        json=payload,
    )

    assert response.status_code == 422


def test_delete_scheduled_payment(client, db_session):
    auth = _register(client, "scheduled-delete@example.com", "+40760777777")
    wallet = _create_wallet(db_session, auth["user"]["id"], "RON")
    created = client.post(
        "/api/v1/payments/scheduled-payments",
        headers=_auth_header(auth),
        json=_payload(wallet),
    ).json()

    delete_response = client.delete(
        f"/api/v1/payments/scheduled-payments/{created['id']}",
        headers=_auth_header(auth),
    )
    assert delete_response.status_code == 204

    get_response = client.get(
        f"/api/v1/payments/scheduled-payments/{created['id']}",
        headers=_auth_header(auth),
    )
    assert get_response.status_code == 404
