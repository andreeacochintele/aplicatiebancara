from decimal import Decimal
from uuid import UUID

from app.notifications.service import NotificationsService
from app.payments.models import BillSplitParticipantStatus, BillSplitStatus
from app.transactions.models import Transaction, TransactionStatus, TransactionType
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


def test_create_and_list_bill_split(client, db_session):
    owner = _register(client, "split-owner@example.com", "+40770111111")
    participant = _register(client, "split-participant@example.com", "+40770222222")

    response = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Dinner",
            "total_amount": "120.00",
            "currency": "RON",
            "participants": [
                {
                    "participant_user_id": participant["user"]["id"],
                    "name": "Dinner friend",
                    "phone": "+40770222222",
                    "amount": "120.00",
                }
            ],
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["owner_user_id"] == owner["user"]["id"]
    assert created["status"] == BillSplitStatus.OPEN
    assert created["participants"][0]["status"] == BillSplitParticipantStatus.PENDING

    owner_list = client.get("/api/v1/payments/bill-splits", headers=_auth_header(owner))
    participant_list = client.get("/api/v1/payments/bill-splits", headers=_auth_header(participant))
    assert [item["id"] for item in owner_list.json()] == [created["id"]]
    assert [item["id"] for item in participant_list.json()] == [created["id"]]


def test_create_bill_split_notifies_the_participant(client, db_session):
    owner = _register(client, "split-notify-owner@example.com", "+40770666601")
    participant = _register(client, "split-notify-participant@example.com", "+40770666602")

    client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Movie night",
            "total_amount": "60.00",
            "currency": "RON",
            "participants": [
                {"participant_user_id": participant["user"]["id"], "name": "Friend", "amount": "60.00"}
            ],
        },
    )

    notifications = NotificationsService(db_session).list_for_user(UUID(participant["user"]["id"]))
    split_notifications = [n for n in notifications if n.type == "SPLIT_BILL"]
    assert len(split_notifications) == 1
    assert "Movie night" in split_notifications[0].message


def test_create_bill_split_from_percent_share(client):
    owner = _register(client, "split-percent-owner@example.com", "+40770333331")
    participant = _register(client, "split-percent-participant@example.com", "+40770333332")

    response = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Dinner",
            "total_amount": "120.00",
            "currency": "RON",
            "participants": [
                {
                    "participant_user_id": participant["user"]["id"],
                    "name": "Dinner friend",
                    "percent": "25",
                }
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["participants"][0]["amount"] == "30.00"


def test_create_bill_split_resolves_participant_by_phone(client):
    owner = _register(client, "split-phone-owner@example.com", "+40770333334")
    participant = _register(client, "split-phone-participant@example.com", "+40770333335")

    response = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Coffee",
            "total_amount": "40.00",
            "currency": "RON",
            "participants": [
                {
                    "name": "Coffee friend",
                    "phone": participant["user"]["phone"],
                    "percent": "50",
                }
            ],
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["participants"][0]["participant_user_id"] == participant["user"]["id"]
    assert created["participants"][0]["amount"] == "20.00"


def test_bill_split_rejects_participant_amounts_above_total(client):
    owner = _register(client, "split-over-total@example.com", "+40770333333")

    response = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Taxi",
            "total_amount": "100.00",
            "currency": "RON",
            "participants": [{"name": "Friend", "phone": "+40779999999", "amount": "140.00"}],
        },
    )

    assert response.status_code == 422


def test_bill_split_does_not_persist_when_a_participant_fails_to_resolve(client):
    # Under the Supabase REST backend, repository.add() is an immediate
    # INSERT with no surrounding transaction -- creating the BillSplit
    # before resolving every participant left an orphaned, participant-less
    # OPEN split behind whenever one participant's phone/user id didn't
    # resolve. create_bill_split now resolves all participants first.
    owner = _register(client, "split-orphan-owner@example.com", "+40770333336")

    response = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Should not persist",
            "total_amount": "80.00",
            "currency": "RON",
            "participants": [{"name": "Ghost", "phone": "+40770333337", "amount": "80.00"}],
        },
    )
    assert response.status_code == 404

    listed = client.get("/api/v1/payments/bill-splits", headers=_auth_header(owner))
    assert listed.json() == []


def test_bill_split_rejects_non_completed_transaction_as_source(client, db_session):
    owner = _register(client, "split-pending-owner@example.com", "+40770333338")
    owner_wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("500.00"))
    pending_transaction = Transaction(
        initiator_user_id=UUID(owner["user"]["id"]),
        source_wallet_id=owner_wallet.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.PROCESSING,
        amount=Decimal("40.00"),
        currency="RON",
        description="Still processing",
    )
    db_session.add(pending_transaction)
    db_session.flush()

    response = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Should fail",
            "total_amount": "40.00",
            "currency": "RON",
            "source_transaction_id": str(pending_transaction.id),
            "participants": [{"name": "Friend", "phone": "+40770333339", "amount": "40.00"}],
        },
    )

    assert response.status_code == 422


def test_bill_split_rejects_incoming_transaction_as_source(client, db_session):
    payer = _register(client, "split-incoming-payer@example.com", "+40770999993")
    owner = _register(client, "split-incoming-owner@example.com", "+40770999994")
    payer_wallet = _create_wallet(db_session, payer["user"]["id"], "RON", Decimal("500.00"))
    owner_wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("0.00"))

    incoming_transaction = TransactionService(db_session).create_internal_transfer(
        UUID(payer["user"]["id"]),
        InternalTransferCreate(
            source_wallet_id=payer_wallet.id,
            destination_wallet_id=owner_wallet.id,
            amount=Decimal("50.00"),
            description="Cashback",
        ),
    )
    db_session.flush()

    response = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Should fail",
            "total_amount": "50.00",
            "currency": "RON",
            "source_transaction_id": str(incoming_transaction.id),
            "participants": [{"name": "Friend", "phone": "+40770999995", "amount": "50.00"}],
        },
    )

    assert response.status_code == 422


def test_participant_can_pay_bill_split(client, db_session):
    owner = _register(client, "split-pay-owner@example.com", "+40770444444")
    participant = _register(client, "split-pay-participant@example.com", "+40770555555")
    owner_wallet = _create_wallet(db_session, owner["user"]["id"], "RON", Decimal("10.00"))
    participant_wallet = _create_wallet(db_session, participant["user"]["id"], "RON", Decimal("200.00"))

    created = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Groceries",
            "total_amount": "80.00",
            "currency": "RON",
            "participants": [
                {
                    "participant_user_id": participant["user"]["id"],
                    "name": "Groceries friend",
                    "amount": "80.00",
                }
            ],
        },
    ).json()
    participant_id = created["participants"][0]["id"]

    response = client.post(
        f"/api/v1/payments/bill-splits/{created['id']}/participants/{participant_id}/pay",
        headers=_auth_header(participant),
        json={"source_wallet_id": str(participant_wallet.id)},
    )

    assert response.status_code == 200
    paid = response.json()
    assert paid["status"] == BillSplitStatus.SETTLED
    assert paid["participants"][0]["status"] == BillSplitParticipantStatus.PAID
    assert paid["participants"][0]["paid_transaction_id"] is not None
    assert participant_wallet.available_balance == Decimal("120.00")
    assert owner_wallet.available_balance == Decimal("90.00")

    owner_notifications = NotificationsService(db_session).list_for_user(UUID(owner["user"]["id"]))
    split_notifications = [n for n in owner_notifications if n.type == "SPLIT_BILL"]
    assert len(split_notifications) == 1
    assert "Groceries" in split_notifications[0].message


def test_participant_can_decline_bill_split(client):
    owner = _register(client, "split-decline-owner@example.com", "+40770555561")
    participant = _register(client, "split-decline-participant@example.com", "+40770555562")

    created = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Ride",
            "total_amount": "40.00",
            "currency": "RON",
            "participants": [
                {
                    "participant_user_id": participant["user"]["id"],
                    "name": "Ride friend",
                    "amount": "20.00",
                }
            ],
        },
    ).json()
    participant_id = created["participants"][0]["id"]

    response = client.post(
        f"/api/v1/payments/bill-splits/{created['id']}/participants/{participant_id}/decline",
        headers=_auth_header(participant),
    )

    assert response.status_code == 200
    assert response.json()["participants"][0]["status"] == BillSplitParticipantStatus.DECLINED


def test_bill_split_is_private_to_owner_and_participants(client):
    owner = _register(client, "split-private-owner@example.com", "+40770666666")
    participant = _register(client, "split-private-participant@example.com", "+40770777777")
    stranger = _register(client, "split-private-stranger@example.com", "+40770888888")

    created = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Lunch",
            "total_amount": "30.00",
            "currency": "RON",
            "participants": [
                {
                    "participant_user_id": participant["user"]["id"],
                    "name": "Lunch friend",
                    "amount": "30.00",
                }
            ],
        },
    ).json()

    response = client.get(f"/api/v1/payments/bill-splits/{created['id']}", headers=_auth_header(stranger))

    assert response.status_code == 404


def test_owner_can_cancel_open_bill_split(client):
    owner = _register(client, "split-cancel-owner@example.com", "+40770999991")
    participant = _register(client, "split-cancel-participant@example.com", "+40770999992")
    created = client.post(
        "/api/v1/payments/bill-splits",
        headers=_auth_header(owner),
        json={
            "title": "Tickets",
            "total_amount": "60.00",
            "currency": "RON",
            "participants": [
                {
                    "participant_user_id": participant["user"]["id"],
                    "name": "Ticket friend",
                    "amount": "60.00",
                }
            ],
        },
    ).json()

    response = client.patch(f"/api/v1/payments/bill-splits/{created['id']}/cancel", headers=_auth_header(owner))

    assert response.status_code == 200
    assert response.json()["status"] == BillSplitStatus.CANCELLED
