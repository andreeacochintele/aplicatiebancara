from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.payments.models import PaymentRequestStatus
from app.payments.schemas import PaymentRequestCreate
from app.payments.service import PaymentRequestService
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


def test_create_payment_request(client, db_session):
    creator = _register(client, "qr-creator@example.com", "+40740111111")
    wallet = _create_wallet(db_session, creator["user"]["id"], "RON")

    response = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={
            "destination_wallet_id": str(wallet.id),
            "amount": "80.00",
            "currency": "RON",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["creator_user_id"] == creator["user"]["id"]
    assert body["destination_wallet_id"] == str(wallet.id)
    assert body["amount"] == "80.00"
    assert body["status"] == PaymentRequestStatus.ACTIVE


def test_list_payment_requests_returns_only_creators_own_requests(client, db_session):
    creator = _register(client, "qr-list-creator@example.com", "+40740211111")
    other = _register(client, "qr-list-other@example.com", "+40740222229")
    creator_wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    other_wallet = _create_wallet(db_session, other["user"]["id"], "RON")

    first = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(creator_wallet.id), "amount": "10.00", "currency": "RON"},
    ).json()
    second = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(creator_wallet.id), "amount": "20.00", "currency": "RON"},
    ).json()
    client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(other),
        json={"destination_wallet_id": str(other_wallet.id), "amount": "30.00", "currency": "RON"},
    )

    response = client.get("/api/v1/payments/payment-requests", headers=_auth_header(creator))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {first["id"], second["id"]}


def test_owner_can_cancel_active_payment_request(client, db_session):
    creator = _register(client, "qr-cancel-creator@example.com", "+40740233330")
    wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    created = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(wallet.id), "amount": "40.00", "currency": "RON"},
    ).json()

    response = client.patch(f"/api/v1/payments/payment-requests/{created['id']}/cancel", headers=_auth_header(creator))

    assert response.status_code == 200
    assert response.json()["status"] == PaymentRequestStatus.CANCELLED

    get_response = client.get(f"/api/v1/payments/payment-requests/{created['id']}", headers=_auth_header(creator))
    assert get_response.status_code == 409


def test_cancel_payment_request_rejects_non_creator(client, db_session):
    creator = _register(client, "qr-cancel-owner@example.com", "+40740244440")
    stranger = _register(client, "qr-cancel-stranger@example.com", "+40740255550")
    wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    created = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(wallet.id), "amount": "40.00", "currency": "RON"},
    ).json()

    response = client.patch(f"/api/v1/payments/payment-requests/{created['id']}/cancel", headers=_auth_header(stranger))

    assert response.status_code == 404


def test_cannot_cancel_an_already_paid_payment_request(client, db_session):
    creator = _register(client, "qr-cancel-paid-creator@example.com", "+40740266660")
    payer = _register(client, "qr-cancel-paid-payer@example.com", "+40740277770")
    destination_wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    source_wallet = _create_wallet(db_session, payer["user"]["id"], "RON", Decimal("200.00"))
    created = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(destination_wallet.id), "amount": "40.00", "currency": "RON"},
    ).json()
    client.post(
        f"/api/v1/payments/payment-requests/{created['id']}/pay",
        headers=_auth_header(payer),
        json={"source_wallet_id": str(source_wallet.id)},
    )

    response = client.patch(f"/api/v1/payments/payment-requests/{created['id']}/cancel", headers=_auth_header(creator))

    assert response.status_code == 409


def test_get_payment_request(client, db_session):
    creator = _register(client, "qr-get-creator@example.com", "+40740222222")
    payer = _register(client, "qr-get-payer@example.com", "+40740233333")
    wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    created = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(wallet.id), "amount": "25.00", "currency": "RON"},
    ).json()

    response = client.get(f"/api/v1/payments/payment-requests/{created['id']}", headers=_auth_header(payer))

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_pay_payment_request_moves_balance_and_marks_paid(client, db_session):
    creator = _register(client, "qr-pay-creator@example.com", "+40740333333")
    payer = _register(client, "qr-pay-payer@example.com", "+40740344444")
    destination_wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    source_wallet = _create_wallet(db_session, payer["user"]["id"], "RON", Decimal("200.00"))
    created = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(destination_wallet.id), "amount": "60.00", "currency": "RON"},
    ).json()

    response = client.post(
        f"/api/v1/payments/payment-requests/{created['id']}/pay",
        headers=_auth_header(payer),
        json={"source_wallet_id": str(source_wallet.id), "description": "QR payment"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == TransactionStatus.COMPLETED
    assert body["amount"] == "60.00"

    db_session.refresh(source_wallet)
    db_session.refresh(destination_wallet)
    assert source_wallet.available_balance == Decimal("140.00")
    assert destination_wallet.available_balance == Decimal("60.00")

    paid_request = client.get(f"/api/v1/payments/payment-requests/{created['id']}", headers=_auth_header(creator))
    assert paid_request.status_code == 409


def test_pay_open_amount_payment_request(client, db_session):
    creator = _register(client, "qr-open-creator@example.com", "+40740444444")
    payer = _register(client, "qr-open-payer@example.com", "+40740455555")
    destination_wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    source_wallet = _create_wallet(db_session, payer["user"]["id"], "RON", Decimal("200.00"))
    created = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(destination_wallet.id), "currency": "RON"},
    ).json()

    response = client.post(
        f"/api/v1/payments/payment-requests/{created['id']}/pay",
        headers=_auth_header(payer),
        json={"source_wallet_id": str(source_wallet.id), "amount": "35.00"},
    )

    assert response.status_code == 201
    assert response.json()["amount"] == "35.00"


def test_payment_request_rejects_creator_as_payer(client, db_session):
    creator = _register(client, "qr-self-creator@example.com", "+40740555555")
    wallet = _create_wallet(db_session, creator["user"]["id"], "RON", Decimal("200.00"))
    created = client.post(
        "/api/v1/payments/payment-requests",
        headers=_auth_header(creator),
        json={"destination_wallet_id": str(wallet.id), "amount": "20.00", "currency": "RON"},
    ).json()

    response = client.post(
        f"/api/v1/payments/payment-requests/{created['id']}/pay",
        headers=_auth_header(creator),
        json={"source_wallet_id": str(wallet.id)},
    )

    assert response.status_code == 422


def test_expired_payment_request_cannot_be_paid(client, db_session):
    creator = _register(client, "qr-expired-creator@example.com", "+40740666666")
    payer = _register(client, "qr-expired-payer@example.com", "+40740677777")
    destination_wallet = _create_wallet(db_session, creator["user"]["id"], "RON")
    source_wallet = _create_wallet(db_session, payer["user"]["id"], "RON", Decimal("200.00"))
    payment_request = PaymentRequestService(db_session).create_payment_request(
        UUID(creator["user"]["id"]),
        PaymentRequestCreate(destination_wallet_id=destination_wallet.id, amount=Decimal("20.00"), currency="RON"),
    )
    payment_request.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    response = client.post(
        f"/api/v1/payments/payment-requests/{payment_request.id}/pay",
        headers=_auth_header(payer),
        json={"source_wallet_id": str(source_wallet.id)},
    )

    assert response.status_code == 409
    assert payment_request.status == PaymentRequestStatus.EXPIRED

