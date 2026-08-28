from datetime import datetime, timezone
from decimal import Decimal

from app.core.enums import UserRole
from app.reconciliation.service import ReconciliationService
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


def _user(db_session, email: str):
    return UserService(db_session).create_user(
        UserCreate(email=email, password="Sup3rSecret!", first_name="Recon", last_name="User")
    )


def _deposit(db_session, wallet, amount: Decimal) -> None:
    """A wallet's very first money has to enter from outside this app's own
    ledger (e.g. an external top-up) — unlike every other test file's
    `wallet.available_balance = X` shortcut, this writes the matching CREDIT
    entry too, so reconciliation (which only cares that a wallet's own
    ledger explains its own balance) sees a consistent wallet, not a bug."""
    transaction = Transaction(
        initiator_user_id=wallet.user_id,
        destination_wallet_id=wallet.id,
        type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=amount,
        currency=wallet.currency,
        description="External deposit (test fixture)",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()
    wallet.available_balance += amount
    db_session.add(
        WalletLedgerEntry(
            wallet_id=wallet.id,
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.CREDIT,
            amount=amount,
            currency=wallet.currency,
            balance_after=wallet.available_balance,
        )
    )
    db_session.flush()


def test_reconciliation_reports_no_discrepancies_for_wallets_touched_only_through_services(db_session):
    sender = _user(db_session, "recon-sender@example.com")
    receiver = _user(db_session, "recon-receiver@example.com")
    sender_wallet = WalletService(db_session).create_wallet(sender.id, WalletCreate(currency="RON", is_main=True))
    receiver_wallet = WalletService(db_session).create_wallet(receiver.id, WalletCreate(currency="RON", is_main=True))
    _deposit(db_session, sender_wallet, Decimal("500.00"))

    TransactionService(db_session).create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id, destination_wallet_id=receiver_wallet.id, amount=Decimal("120.00")
        ),
    )
    db_session.flush()

    report = ReconciliationService(db_session).check_all_wallets()

    assert report.wallets_checked == 2
    assert report.discrepancies == []


def test_reconciliation_flags_a_balance_that_does_not_match_its_ledger(db_session):
    user = _user(db_session, "recon-tampered@example.com")
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON", is_main=True))
    transaction = Transaction(
        initiator_user_id=user.id,
        source_wallet_id=wallet.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("50.00"),
        currency="RON",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()
    db_session.add(
        WalletLedgerEntry(
            wallet_id=wallet.id,
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=Decimal("50.00"),
            currency="RON",
            balance_after=Decimal("-50.00"),
        )
    )
    # Simulates exactly the class of bug reconciliation exists to catch: the
    # ledger says -50.00, but the stored balance disagrees.
    wallet.available_balance = Decimal("0.00")
    db_session.flush()

    report = ReconciliationService(db_session).check_all_wallets()

    assert len(report.discrepancies) == 1
    discrepancy = report.discrepancies[0]
    assert discrepancy.wallet_id == wallet.id
    assert discrepancy.stored_total_balance == Decimal("0.00")
    assert discrepancy.ledger_derived_balance == Decimal("-50.00")
    assert discrepancy.difference == Decimal("50.00")


def test_reconciliation_ignores_hold_and_release_entries(db_session):
    """A HOLD followed by a RELEASE only ever moves money between
    available_balance and reserved_balance — their sum (what reconciliation
    checks) must never look like a discrepancy just because of that
    movement."""
    user = _user(db_session, "recon-hold@example.com")
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON", is_main=True))
    _deposit(db_session, wallet, Decimal("1000.00"))

    transaction = Transaction(
        initiator_user_id=user.id,
        source_wallet_id=wallet.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.REJECTED,
        amount=Decimal("300.00"),
        currency="RON",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()

    wallet.available_balance -= Decimal("300.00")
    wallet.reserved_balance += Decimal("300.00")
    db_session.add(
        WalletLedgerEntry(
            wallet_id=wallet.id,
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.HOLD,
            amount=Decimal("300.00"),
            currency="RON",
            balance_after=wallet.available_balance,
        )
    )
    db_session.flush()

    wallet.reserved_balance -= Decimal("300.00")
    wallet.available_balance += Decimal("300.00")
    db_session.add(
        WalletLedgerEntry(
            wallet_id=wallet.id,
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.RELEASE,
            amount=Decimal("300.00"),
            currency="RON",
            balance_after=wallet.available_balance,
        )
    )
    db_session.flush()

    report = ReconciliationService(db_session).check_all_wallets()

    assert report.discrepancies == []


def test_reconciliation_endpoint_requires_admin(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "recon-http@example.com",
            "phone": "+40744444460",
            "password": "Sup3rSecret!",
            "first_name": "Recon",
            "last_name": "Http",
        },
    )
    token = register.json()["tokens"]["access_token"]

    response = client.get("/api/v1/admin/reconciliation", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_reconciliation_endpoint_returns_a_report_for_admin(client, db_session):
    admin = _user(db_session, "recon-admin@example.com")
    admin.role = UserRole.ADMIN
    db_session.commit()

    login = client.post("/api/v1/auth/login", json={"email": "recon-admin@example.com", "password": "Sup3rSecret!"})
    token = login.json()["tokens"]["access_token"]

    response = client.get("/api/v1/admin/reconciliation", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert "wallets_checked" in body
    assert body["discrepancies"] == []
