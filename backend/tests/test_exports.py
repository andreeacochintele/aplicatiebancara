from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.enums import UserType
from app.core.exceptions import NotFoundError, ValidationError
from app.exports.schemas import TransactionExportRequest
from app.exports.service import ExportService
from app.merchants.schemas import MerchantCreate
from app.merchants.service import MerchantService
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def wallets_with_transfer(db_session):
    users = UserService(db_session)
    wallets = WalletService(db_session)

    business = users.create_user(
        UserCreate(
            email="export-business@example.com",
            password="Sup3rSecret!",
            first_name="Biz",
            last_name="Owner",
            user_type=UserType.BUSINESS,
        )
    )
    receiver = users.create_user(
        UserCreate(email="export-receiver@example.com", password="Sup3rSecret!", first_name="Rece", last_name="Iver")
    )
    business_wallet = wallets.create_wallet(business.id, WalletCreate(currency="RON"))
    receiver_wallet = wallets.create_wallet(receiver.id, WalletCreate(currency="RON"))
    business_wallet.available_balance = Decimal("500.00")
    db_session.flush()

    TransactionService(db_session).create_internal_transfer(
        business.id,
        InternalTransferCreate(
            source_wallet_id=business_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("120.00"),
            description="Rent",
        ),
    )
    db_session.flush()

    return business, business_wallet, receiver, receiver_wallet


def _today_range():
    return date.today() - timedelta(days=1), date.today() + timedelta(days=1)


def test_export_lists_outgoing_transaction_for_business_sender(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    rows = ExportService(db_session).list_transactions(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to)
    )

    assert len(rows) == 1
    assert rows[0].amount == Decimal("120.00")
    assert rows[0].currency == "RON"
    assert rows[0].description == "Rent"
    assert rows[0].type == TransactionType.TRANSFER


def test_export_direction_filter_excludes_non_matching_entries(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    incoming = ExportService(db_session).list_transactions(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, direction="incoming")
    )
    outgoing = ExportService(db_session).list_transactions(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, direction="outgoing")
    )

    assert incoming == []
    assert len(outgoing) == 1


def test_export_wallet_filter_narrows_to_one_wallet(db_session, wallets_with_transfer):
    business, business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    rows = ExportService(db_session).list_transactions(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, wallet_id=business_wallet.id)
    )

    assert len(rows) == 1


def test_export_rejects_another_users_wallet(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    with pytest.raises(NotFoundError):
        ExportService(db_session).list_transactions(
            business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, wallet_id=receiver_wallet.id)
        )


def test_export_status_filter(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    completed = ExportService(db_session).list_transactions(
        business.id,
        TransactionExportRequest(date_from=date_from, date_to=date_to, status=TransactionStatus.COMPLETED),
    )
    failed = ExportService(db_session).list_transactions(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, status=TransactionStatus.FAILED)
    )

    assert len(completed) == 1
    assert failed == []


def test_export_excludes_entries_outside_period(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    future_from = date.today() + timedelta(days=10)
    future_to = date.today() + timedelta(days=20)

    rows = ExportService(db_session).list_transactions(
        business.id, TransactionExportRequest(date_from=future_from, date_to=future_to)
    )

    assert rows == []


def test_export_rejects_inverted_date_range(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer

    with pytest.raises(ValidationError):
        ExportService(db_session).list_transactions(
            business.id,
            TransactionExportRequest(date_from=date.today(), date_to=date.today() - timedelta(days=1)),
        )


def test_export_resolves_merchant_counterparty(db_session, wallets_with_transfer):
    business, business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    merchant = MerchantService(db_session).create_merchant(MerchantCreate(name="CoffeeCo", category="Food"))
    card_payment = Transaction(
        initiator_user_id=business.id,
        source_wallet_id=business_wallet.id,
        merchant_id=merchant.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("15.00"),
        currency="RON",
        description="Coffee",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(card_payment)
    db_session.flush()
    db_session.add(
        WalletLedgerEntry(
            wallet_id=business_wallet.id,
            transaction_id=card_payment.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=Decimal("15.00"),
            currency="RON",
            balance_after=Decimal("365.00"),
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    date_from, date_to = _today_range()

    rows = ExportService(db_session).list_transactions(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, currency="RON")
    )

    coffee_row = next(row for row in rows if row.description == "Coffee")
    assert coffee_row.counterparty == "CoffeeCo"


def test_export_csv_contains_expected_columns_and_values(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)

    rows = service.list_transactions(business.id, TransactionExportRequest(date_from=date_from, date_to=date_to))
    csv_text = service.to_csv(rows)

    header = csv_text.splitlines()[0]
    assert header == "date,transaction_id,type,counterparty,description,amount,currency,status"
    assert "Rent" in csv_text
    assert "120.00" in csv_text


def test_export_endpoint_rejects_personal_user(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "export-personal@example.com",
            "phone": "+40744444450",
            "password": "Sup3rSecret!",
            "first_name": "Per",
            "last_name": "Sonal",
        },
    )
    assert register.status_code == 201
    token = register.json()["tokens"]["access_token"]

    response = client.get(
        "/api/v1/exports/transactions",
        headers={"Authorization": f"Bearer {token}"},
        params={"date_from": str(date.today()), "date_to": str(date.today())},
    )

    assert response.status_code == 403


def test_export_endpoint_returns_csv_for_business_user(client, db_session):
    # RegisterRequest has no user_type field (no business signup flow yet via
    # HTTP) — seed the business user directly, same as seed.py does, then log
    # in over HTTP for a real token.
    UserService(db_session).create_user(
        UserCreate(
            email="export-biz-http@example.com",
            phone="+40744444451",
            password="Sup3rSecret!",
            first_name="Biz",
            last_name="Http",
            user_type=UserType.BUSINESS,
        )
    )
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login", json={"email": "export-biz-http@example.com", "password": "Sup3rSecret!"}
    )
    assert login.status_code == 200
    token = login.json()["tokens"]["access_token"]
    date_from, date_to = _today_range()

    response = client.get(
        "/api/v1/exports/transactions",
        headers={"Authorization": f"Bearer {token}"},
        params={"date_from": str(date_from), "date_to": str(date_to)},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines()[0] == "date,transaction_id,type,counterparty,description,amount,currency,status"
