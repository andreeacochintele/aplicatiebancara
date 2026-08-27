import uuid
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.iban import generate_iban
from app.wallets.models import WalletStatus
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


def test_new_wallet_gets_an_iban(db_session, seeded_user):
    service = WalletService(db_session)
    wallet = service.create_wallet(seeded_user.id, WalletCreate(currency="ron"))

    assert wallet.iban.startswith("RO")
    assert len(wallet.iban) == 24


def test_each_wallet_gets_a_distinct_iban(db_session, seeded_user):
    service = WalletService(db_session)
    ron = service.create_wallet(seeded_user.id, WalletCreate(currency="ron"))
    eur = service.create_wallet(seeded_user.id, WalletCreate(currency="eur"))

    assert ron.iban != eur.iban


def test_generate_iban_produces_a_checksum_valid_iban():
    iban = generate_iban()

    assert len(iban) == 24
    assert iban[:2] == "RO"
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
    assert int(numeric) % 97 == 1


def test_oversized_currency_code_is_rejected(db_session, seeded_user):
    service = WalletService(db_session)

    with pytest.raises(ValidationError):
        service.create_wallet(seeded_user.id, WalletCreate(currency="ABCDEFGH"))


def test_unsupported_currency_code_is_rejected(db_session, seeded_user):
    service = WalletService(db_session)

    with pytest.raises(ValidationError):
        service.create_wallet(seeded_user.id, WalletCreate(currency="ZZZ"))


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


def test_close_wallet_sweeps_cross_currency_balance_into_main(db_session, seeded_user):
    service = WalletService(db_session)
    main = service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    eur = service.create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    eur.available_balance = Decimal("100.00")
    db_session.flush()

    closed = service.close_wallet(seeded_user.id, eur.id)

    assert closed.status == WalletStatus.CLOSED
    assert closed.available_balance == Decimal("0.00")
    refreshed_main = service.repository.get_by_id(main.id)
    # 100 EUR * 4.97 RON/EUR, minus the standard 0.5% fee, same as any other quote.
    assert refreshed_main.available_balance == Decimal("494.52")


def test_close_wallet_rejects_the_main_wallet(db_session, seeded_user):
    service = WalletService(db_session)
    main = service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    service.create_wallet(seeded_user.id, WalletCreate(currency="EUR"))

    with pytest.raises(ValidationError):
        service.close_wallet(seeded_user.id, main.id)


def test_close_wallet_rejects_wallet_with_funds_on_hold(db_session, seeded_user):
    service = WalletService(db_session)
    service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    eur = service.create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    eur.reserved_balance = Decimal("10.00")
    db_session.flush()

    with pytest.raises(ValidationError):
        service.close_wallet(seeded_user.id, eur.id)


def test_close_wallet_rejects_already_closed_wallet(db_session, seeded_user):
    service = WalletService(db_session)
    service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    eur = service.create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    service.close_wallet(seeded_user.id, eur.id)

    with pytest.raises(ValidationError):
        service.close_wallet(seeded_user.id, eur.id)


def test_currency_can_be_reopened_after_closing(db_session, seeded_user):
    service = WalletService(db_session)
    service.create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    eur = service.create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    service.close_wallet(seeded_user.id, eur.id)

    reopened = service.create_wallet(seeded_user.id, WalletCreate(currency="EUR"))

    assert reopened.status == WalletStatus.ACTIVE
    assert reopened.available_balance == Decimal("0")


def test_oversized_currency_returns_422_not_a_bare_500(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "wallet-http@example.com",
            "phone": "+40744444445",
            "password": "Sup3rSecret!",
            "first_name": "Wallet",
            "last_name": "Http",
        },
    )
    assert register.status_code == 201
    token = register.json()["tokens"]["access_token"]

    response = client.post(
        "/api/v1/wallets",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": "ABCDEFGH"},
    )

    assert response.status_code == 422
