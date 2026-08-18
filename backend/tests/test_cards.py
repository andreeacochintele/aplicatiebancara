import uuid

import pytest

from app.cards.models import CardStatus, CardType
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import NotFoundError, ValidationError
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.models import WalletStatus
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def user_with_wallet(db_session):
    user = UserService(db_session).create_user(
        UserCreate(
            email="card-owner@example.com",
            password="Sup3rSecret!",
            first_name="Card",
            last_name="Owner",
        )
    )
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    return user, wallet


def test_create_mock_debit_card(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    card = CardService(db_session).create_card(user.id, CardCreate(default_wallet_id=wallet.id))

    assert card.id is not None
    assert card.user_id == user.id
    assert card.default_wallet_id == wallet.id
    assert card.type == CardType.DEBIT
    assert card.status == CardStatus.ACTIVE
    assert card.masked_pan == f"**** **** **** {card.last_four}"
    assert len(card.last_four) == 4


def test_one_time_card_starts_with_one_remaining_use(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    card = CardService(db_session).create_card(
        user.id,
        CardCreate(type=CardType.ONE_TIME, default_wallet_id=wallet.id),
    )

    assert card.type == CardType.ONE_TIME
    assert card.one_time_remaining == 1


def test_create_card_rejects_other_users_wallet(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    other = UserService(db_session).create_user(
        UserCreate(
            email="other-card-owner@example.com",
            password="Sup3rSecret!",
            first_name="Other",
            last_name="Owner",
        )
    )
    other_wallet = WalletService(db_session).create_wallet(other.id, WalletCreate(currency="EUR"))

    with pytest.raises(NotFoundError):
        CardService(db_session).create_card(user.id, CardCreate(default_wallet_id=other_wallet.id))


def test_create_card_rejects_frozen_default_wallet(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    wallet.status = WalletStatus.FROZEN

    with pytest.raises(ValidationError):
        CardService(db_session).create_card(user.id, CardCreate(default_wallet_id=wallet.id))


def test_list_cards_is_scoped_to_user(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    service = CardService(db_session)
    own_card = service.create_card(user.id, CardCreate(default_wallet_id=wallet.id))
    other = UserService(db_session).create_user(
        UserCreate(
            email="card-list-other@example.com",
            password="Sup3rSecret!",
            first_name="List",
            last_name="Other",
        )
    )
    service.create_card(other.id, CardCreate())

    assert service.list_cards(user.id) == [own_card]


def test_freeze_and_unfreeze_card(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    service = CardService(db_session)
    card = service.create_card(user.id, CardCreate(default_wallet_id=wallet.id))

    frozen = service.freeze_card(user.id, card.id)
    assert frozen.status == CardStatus.FROZEN

    active = service.unfreeze_card(user.id, card.id)
    assert active.status == CardStatus.ACTIVE


def test_user_cannot_modify_another_users_card(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    other = UserService(db_session).create_user(
        UserCreate(
            email="card-security-other@example.com",
            password="Sup3rSecret!",
            first_name="Security",
            last_name="Other",
        )
    )
    card = CardService(db_session).create_card(other.id, CardCreate())

    with pytest.raises(NotFoundError):
        CardService(db_session).freeze_card(user.id, card.id)


def test_unknown_card_is_not_found(db_session, user_with_wallet):
    user, _wallet = user_with_wallet

    with pytest.raises(NotFoundError):
        CardService(db_session).get_for_user(user.id, uuid.uuid4())
