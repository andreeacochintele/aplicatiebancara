from decimal import Decimal

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.transactions.payment_proof import PaymentProofService
from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def completed_transfer(db_session):
    """A settled transfer between two people, plus the sender — the ordinary
    case someone actually asks a bank for a confirmation of."""
    users = UserService(db_session)
    wallets = WalletService(db_session)

    sender = users.create_user(
        UserCreate(email="payer@example.com", password="Sup3rSecret!", first_name="Ana", last_name="Pop")
    )
    receiver = users.create_user(
        UserCreate(email="payee@example.com", password="Sup3rSecret!", first_name="Dan", last_name="Ion")
    )
    sender_wallet = wallets.create_wallet(sender.id, WalletCreate(currency="RON"))
    receiver_wallet = wallets.create_wallet(receiver.id, WalletCreate(currency="RON"))
    sender_wallet.available_balance = Decimal("500.00")
    db_session.flush()

    transaction = TransactionService(db_session).create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("120.00"),
            description="Rent share",
        ),
    )
    db_session.flush()
    return sender, receiver, transaction


def test_generates_a_pdf_naming_both_parties(db_session, completed_transfer):
    sender, _receiver, transaction = completed_transfer

    content, filename = PaymentProofService(db_session).generate(sender.id, transaction.id)

    assert content.startswith(b"%PDF-")
    assert filename == f"payment_proof_{str(transaction.id)[:8]}.pdf"

    payer, payee = PaymentProofService(db_session)._parties(transaction)
    assert payer.name == "Ana Pop"
    assert payee.name == "Dan Ion"


def test_the_same_transfer_reads_as_sent_or_received_depending_on_who_asks(db_session, completed_transfer):
    sender, receiver, transaction = completed_transfer
    service = PaymentProofService(db_session)

    assert service._heading(sender.id, transaction)[0] == "Payment sent"
    assert service._heading(receiver.id, transaction)[0] == "Payment received"


def test_another_users_transaction_is_not_disclosed(db_session, completed_transfer):
    _sender, _receiver, transaction = completed_transfer
    stranger = UserService(db_session).create_user(
        UserCreate(email="stranger@example.com", password="Sup3rSecret!", first_name="Not", last_name="Mine")
    )

    # The document names both parties and their IBANs, so this must 404
    # rather than render for anyone who was not part of the payment.
    with pytest.raises(NotFoundError):
        PaymentProofService(db_session).generate(stranger.id, transaction.id)


def test_a_transaction_that_has_not_settled_has_no_confirmation(db_session, completed_transfer):
    sender, _receiver, transaction = completed_transfer
    transaction.status = TransactionStatus.PENDING_REVIEW
    db_session.flush()

    with pytest.raises(ValidationError):
        PaymentProofService(db_session).generate(sender.id, transaction.id)


def test_external_beneficiary_is_recovered_from_the_description():
    # An off-us IBAN transfer stores no destination wallet; payments/service.py
    # records the payee only inside the description it generates.
    transaction = Transaction(
        type=TransactionType.TRANSFER,
        description="Transfer to Maria Dinu - RO49EASY1234567890123456",
    )

    party = PaymentProofService._described_party(transaction)

    assert party is not None
    assert party.name == "Maria Dinu"
    assert party.account == "RO49EASY1234567890123456"


def test_a_user_written_description_is_not_mistaken_for_a_beneficiary():
    transaction = Transaction(type=TransactionType.TRANSFER, description="Rent for August")

    assert PaymentProofService._described_party(transaction) is None


def test_an_unknown_counterparty_is_not_passed_off_as_the_bank():
    # Only types whose other side really is EasyB may be labelled EasyB —
    # otherwise the document would assert the money went somewhere it didn't.
    cashback = Transaction(type=TransactionType.CASHBACK)
    transfer = Transaction(type=TransactionType.TRANSFER)

    assert PaymentProofService._fallback_party(cashback).name == "EasyB"
    assert PaymentProofService._fallback_party(transfer).name == "Not recorded"


def test_a_bic_suffix_does_not_hide_the_beneficiary():
    # payments/service.py appends " (BIC: ...)" for non-IBAN accounts; the
    # payee must still be recovered rather than falling back to "Not recorded".
    transaction = Transaction(
        type=TransactionType.TRANSFER,
        description="Transfer to Maria Dinu - US1234567890 (BIC: CHASUS33)",
    )

    party = PaymentProofService._described_party(transaction)

    assert party is not None
    assert party.name == "Maria Dinu"
    assert party.account == "US1234567890"
