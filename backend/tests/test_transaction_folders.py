from decimal import Decimal
from uuid import UUID

from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
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


def test_create_update_list_and_delete_transaction_folder(client):
    auth = _register(client, "folder-owner@example.com", "+40771111111")

    create_response = client.post(
        "/api/v1/payments/transaction-folders",
        headers=_auth_header(auth),
        json={"name": "Rent", "color": "violet", "description": "Apartment costs"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["owner_user_id"] == auth["user"]["id"]
    assert created["name"] == "Rent"
    assert created["items"] == []

    update_response = client.patch(
        f"/api/v1/payments/transaction-folders/{created['id']}",
        headers=_auth_header(auth),
        json={"name": "Home", "color": "blue"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Home"

    list_response = client.get("/api/v1/payments/transaction-folders", headers=_auth_header(auth))
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    delete_response = client.delete(
        f"/api/v1/payments/transaction-folders/{created['id']}",
        headers=_auth_header(auth),
    )
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/v1/payments/transaction-folders/{created['id']}", headers=_auth_header(auth))
    assert get_response.status_code == 404


def test_transaction_folder_rejects_duplicate_name(client):
    auth = _register(client, "folder-duplicate@example.com", "+40771222222")
    payload = {"name": "Taxes"}
    first = client.post("/api/v1/payments/transaction-folders", headers=_auth_header(auth), json=payload)
    second = client.post("/api/v1/payments/transaction-folders", headers=_auth_header(auth), json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_add_and_remove_transaction_from_folder(client, db_session):
    owner = _register(client, "folder-tx-owner@example.com", "+40771333333")
    receiver = _register(client, "folder-tx-receiver@example.com", "+40771444444")
    owner_wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("500.00"))
    receiver_wallet = _create_wallet(db_session, receiver["user"]["id"], "RON")
    transaction = TransactionService(db_session).create_internal_transfer(
        UUID(owner["user"]["id"]),
        InternalTransferCreate(
            source_wallet_id=owner_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("75.00"),
            description="Folder me",
        ),
    )
    folder = client.post(
        "/api/v1/payments/transaction-folders",
        headers=_auth_header(owner),
        json={"name": "Shared costs"},
    ).json()

    add_response = client.post(
        f"/api/v1/payments/transaction-folders/{folder['id']}/transactions",
        headers=_auth_header(owner),
        json={"transaction_id": str(transaction.id)},
    )

    assert add_response.status_code == 200
    assert add_response.json()["items"][0]["transaction_id"] == str(transaction.id)

    duplicate_response = client.post(
        f"/api/v1/payments/transaction-folders/{folder['id']}/transactions",
        headers=_auth_header(owner),
        json={"transaction_id": str(transaction.id)},
    )
    assert duplicate_response.status_code == 409

    remove_response = client.delete(
        f"/api/v1/payments/transaction-folders/{folder['id']}/transactions/{transaction.id}",
        headers=_auth_header(owner),
    )
    assert remove_response.status_code == 204


def test_transaction_folder_rejects_other_users_transaction(client, db_session):
    owner = _register(client, "folder-private-owner@example.com", "+40771555555")
    other = _register(client, "folder-private-other@example.com", "+40771666666")
    receiver = _register(client, "folder-private-receiver@example.com", "+40771777777")
    other_wallet = _create_wallet(db_session, other["user"]["id"], "RON", Decimal("500.00"))
    receiver_wallet = _create_wallet(db_session, receiver["user"]["id"], "RON")
    transaction = TransactionService(db_session).create_internal_transfer(
        UUID(other["user"]["id"]),
        InternalTransferCreate(
            source_wallet_id=other_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("25.00"),
        ),
    )
    folder = client.post(
        "/api/v1/payments/transaction-folders",
        headers=_auth_header(owner),
        json={"name": "Private"},
    ).json()

    response = client.post(
        f"/api/v1/payments/transaction-folders/{folder['id']}/transactions",
        headers=_auth_header(owner),
        json={"transaction_id": str(transaction.id)},
    )

    assert response.status_code == 404
