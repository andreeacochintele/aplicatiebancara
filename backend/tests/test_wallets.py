import uuid
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(
            email="wallet-owner@example.com",
            phone="+40744444444",
            password="Sup3rSecret!",
            first_name="Wallet",
            last_name="Owner",
        )
    )


def test_first_wallet_is_automatically_main(db_session, seeded_user):
    service = WalletService(db_session)
    wallet = service.create_wallet(seeded_user.id, WalletCreate(currency="ron"))

    assert wallet.currency == "RON"
    assert wallet.is_main is True
    assert wallet.available_balance == Decimal("0")


def test_duplicate_currency_wallet_rejected(db_session, seeded_user):
    service = WalletService(db_session)
    service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))

    with pytest.raises(ConflictError):
        service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))


def test_only_one_main_wallet(db_session, seeded_user):
    service = WalletService(db_session)
    ron = service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    eur = service.create_wallet(seeded_user.id, WalletCreate(currency="EUR", is_main=True))

    assert eur.is_main is True
    assert ron.is_main is False


def test_set_main_wallet_switches_the_flag(db_session, seeded_user):
    service = WalletService(db_session)
    ron = service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    eur = service.create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    assert ron.is_main is True
    assert eur.is_main is False

    updated = service.set_main_wallet(seeded_user.id, eur.id)

    assert updated.is_main is True
    wallets = {wallet.currency: wallet for wallet in service.list_wallets(seeded_user.id)}
    assert wallets["EUR"].is_main is True
    assert wallets["RON"].is_main is False


def test_set_main_wallet_unknown_wallet_raises(db_session, seeded_user):
    service = WalletService(db_session)
    service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))

    with pytest.raises(NotFoundError):
        service.set_main_wallet(seeded_user.id, uuid.uuid4())
