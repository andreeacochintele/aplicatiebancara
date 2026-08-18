from decimal import Decimal
from uuid import UUID

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


def test_phone_lookup_returns_recipient_preview(client, db_session):
    sender = _register(client, "phone-sender@example.com", "+40731111111")
    recipient = _register(client, "phone-recipient@example.com", "+40732222222")
    recipient_wallet = _create_wallet(db_session, recipient["user"]["id"], "RON")

    response = client.post(
        "/api/v1/payments/phone/lookup",
        headers=_auth_header(sender),
        json={"phone": "+40732222222"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == recipient["user"]["id"]
    assert body["phone"] == "+40732222222"
    assert body["destination_wallet_id"] == str(recipient_wallet.id)
    assert body["destination_wallet_currency"] == "RON"


def test_phone_lookup_rejects_unknown_phone(client):
    sender = _register(client, "phone-unknown@example.com", "+40733333333")

    response = client.post(
        "/api/v1/payments/phone/lookup",
        headers=_auth_header(sender),
        json={"phone": "+40739999999"},
    )

    assert response.status_code == 404


def test_phone_lookup_rejects_self(client, db_session):
    sender = _register(client, "phone-self@example.com", "+40734444444")
    _create_wallet(db_session, sender["user"]["id"], "RON")

    response = client.post(
        "/api/v1/payments/phone/lookup",
        headers=_auth_header(sender),
        json={"phone": "+40734444444"},
    )

    assert response.status_code == 422


def test_phone_transfer_moves_balance_and_writes_ledger(client, db_session):
    sender = _register(client, "phone-transfer-sender@example.com", "+40735555555")
    recipient = _register(client, "phone-transfer-recipient@example.com", "+40736666666")
    sender_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("500.00"))
    recipient_wallet = _create_wallet(db_session, recipient["user"]["id"], "RON")

    response = client.post(
        "/api/v1/payments/phone/transfer",
        headers=_auth_header(sender),
        json={
            "phone": "+40736666666",
            "source_wallet_id": str(sender_wallet.id),
            "amount": "125.00",
            "description": "Phone transfer test",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == TransactionStatus.COMPLETED
    assert body["destination_wallet_id"] == str(recipient_wallet.id)
    assert body["amount"] == "125.00"
    assert body["currency"] == "RON"

    db_session.refresh(sender_wallet)
    db_session.refresh(recipient_wallet)
    assert sender_wallet.available_balance == Decimal("375.00")
    assert recipient_wallet.available_balance == Decimal("125.00")


def test_phone_transfer_rejects_recipient_without_matching_currency_wallet(client, db_session):
    sender = _register(client, "phone-no-wallet-sender@example.com", "+40737777777")
    recipient = _register(client, "phone-no-wallet-recipient@example.com", "+40738888888")
    sender_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("500.00"))
    _create_wallet(db_session, recipient["user"]["id"], "EUR")

    response = client.post(
        "/api/v1/payments/phone/transfer",
        headers=_auth_header(sender),
        json={
            "phone": "+40738888888",
            "source_wallet_id": str(sender_wallet.id),
            "amount": "50.00",
        },
    )

    assert response.status_code == 404


def test_phone_transfer_rejects_insufficient_balance(client, db_session):
    sender = _register(client, "phone-low-balance-sender@example.com", "+40739111111")
    recipient = _register(client, "phone-low-balance-recipient@example.com", "+40739222222")
    sender_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("10.00"))
    _create_wallet(db_session, recipient["user"]["id"], "RON")

    response = client.post(
        "/api/v1/payments/phone/transfer",
        headers=_auth_header(sender),
        json={
            "phone": "+40739222222",
            "source_wallet_id": str(sender_wallet.id),
            "amount": "50.00",
        },
    )

    assert response.status_code == 409
