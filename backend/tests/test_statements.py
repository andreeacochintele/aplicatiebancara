from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.statements.schemas import StatementRequest
from app.statements.service import StatementService
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

    sender = users.create_user(
        UserCreate(email="stmt-sender@example.com", password="Sup3rSecret!", first_name="Send", last_name="Er")
    )
    receiver = users.create_user(
        UserCreate(email="stmt-receiver@example.com", password="Sup3rSecret!", first_name="Rece", last_name="Iver")
    )
    sender_wallet = wallets.create_wallet(sender.id, WalletCreate(currency="RON"))
    receiver_wallet = wallets.create_wallet(receiver.id, WalletCreate(currency="RON"))
    sender_wallet.available_balance = Decimal("500.00")
    db_session.flush()

    TransactionService(db_session).create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("120.00"),
            description="Rent",
        ),
    )
    db_session.flush()

    return sender, sender_wallet, receiver, receiver_wallet


def _today_range():
    return date.today() - timedelta(days=1), date.today() + timedelta(days=1)


def test_statement_computes_balances_and_totals(db_session, wallets_with_transfer):
    sender, sender_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    statement = StatementService(db_session).generate(
        sender.id, StatementRequest(wallet_id=sender_wallet.id, date_from=date_from, date_to=date_to)
    )

    assert statement.opening_balance == Decimal("500.00")
    assert statement.closing_balance == Decimal("380.00")
    assert statement.total_outgoing == Decimal("120.00")
    assert statement.total_incoming == Decimal("0")
    assert len(statement.transactions) == 1
    assert statement.transactions[0].direction == "OUT"
    assert statement.transactions[0].amount == Decimal("120.00")


def test_statement_for_receiver_shows_incoming(db_session, wallets_with_transfer):
    _sender, _sender_wallet, receiver, receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    statement = StatementService(db_session).generate(
        receiver.id, StatementRequest(wallet_id=receiver_wallet.id, date_from=date_from, date_to=date_to)
    )

    assert statement.opening_balance == Decimal("0")
    assert statement.closing_balance == Decimal("120.00")
    assert statement.total_incoming == Decimal("120.00")
    assert statement.transactions[0].direction == "IN"


def test_statement_excludes_entries_outside_period(db_session, wallets_with_transfer):
    sender, sender_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    future_from = date.today() + timedelta(days=10)
    future_to = date.today() + timedelta(days=20)

    statement = StatementService(db_session).generate(
        sender.id, StatementRequest(wallet_id=sender_wallet.id, date_from=future_from, date_to=future_to)
    )

    assert statement.transactions == []
    assert statement.opening_balance == statement.closing_balance == sender_wallet.available_balance


def test_statement_rejects_other_users_wallet(db_session, wallets_with_transfer):
    _sender, sender_wallet, receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    with pytest.raises(NotFoundError):
        StatementService(db_session).generate(
            receiver.id, StatementRequest(wallet_id=sender_wallet.id, date_from=date_from, date_to=date_to)
        )


def test_statement_rejects_inverted_date_range(db_session, wallets_with_transfer):
    sender, sender_wallet, _receiver, _receiver_wallet = wallets_with_transfer

    with pytest.raises(ValidationError):
        StatementService(db_session).generate(
            sender.id,
            StatementRequest(wallet_id=sender_wallet.id, date_from=date.today(), date_to=date.today() - timedelta(days=1)),
        )


def test_statement_csv_and_pdf_export(db_session, wallets_with_transfer):
    sender, sender_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = StatementService(db_session)
    statement = service.generate(
        sender.id, StatementRequest(wallet_id=sender_wallet.id, date_from=date_from, date_to=date_to)
    )

    csv_text = service.to_csv(statement)
    assert "Rent" in csv_text
    assert "120.00" in csv_text

    pdf_bytes = service.to_pdf(statement)
    assert pdf_bytes[:4] == b"%PDF"
