from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.transactions.models import TransactionStatus
from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def two_ron_wallets(db_session):
    users = UserService(db_session)
    wallets = WalletService(db_session)

    sender = users.create_user(
        UserCreate(email="sender@example.com", password="Sup3rSecret!", first_name="Send", last_name="Er")
    )
    receiver = users.create_user(
        UserCreate(email="receiver@example.com", password="Sup3rSecret!", first_name="Rece", last_name="Iver")
    )

    sender_wallet = wallets.create_wallet(sender.id, WalletCreate(currency="RON"))
    receiver_wallet = wallets.create_wallet(receiver.id, WalletCreate(currency="RON"))
    sender_wallet.available_balance = Decimal("500.00")
    db_session.flush()

    return sender, sender_wallet, receiver_wallet


def test_internal_transfer_moves_balance_and_writes_ledger(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    transaction = service.create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("100.00"),
            description="Test transfer",
        ),
    )

    assert transaction.status == TransactionStatus.COMPLETED
    assert sender_wallet.available_balance == Decimal("400.00")
    assert receiver_wallet.available_balance == Decimal("100.00")
    assert len(transaction.ledger_entries) == 2


def test_transfer_rejects_insufficient_balance(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    with pytest.raises(ConflictError):
        service.create_internal_transfer(
            sender.id,
            InternalTransferCreate(
                source_wallet_id=sender_wallet.id,
                destination_wallet_id=receiver_wallet.id,
                amount=Decimal("999999.00"),
            ),
        )


def test_transfer_rejects_non_positive_amount(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    with pytest.raises(ValidationError):
        service.create_internal_transfer(
            sender.id,
            InternalTransferCreate(
                source_wallet_id=sender_wallet.id,
                destination_wallet_id=receiver_wallet.id,
                amount=Decimal("0.00"),
            ),
        )
