import uuid
from decimal import Decimal

import pytest

from app.cards.models import CardStatus, CardTier, CardType
from app.cards.repository import CardRepository
from app.cards.schemas import CardCreate, CardPaymentPreferencesUpdate
from app.cards.service import CardService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
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
    assert card.tier == CardTier.REGULAR
    assert card.status == CardStatus.ACTIVE
    assert card.masked_pan == f"**** **** **** {card.last_four}"
    assert len(card.last_four) == 4
    assert len(card.mock_pan) == 19
    assert card.mock_pan.endswith(card.last_four)
    assert card.mock_pan != card.masked_pan
    assert len(card.mock_cvv) == 3
    assert card.mock_cvv.isdigit()


def test_one_time_card_starts_with_one_remaining_use(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    card = CardService(db_session).create_card(
        user.id,
        CardCreate(type=CardType.ONE_TIME, default_wallet_id=wallet.id),
    )

    assert card.type == CardType.ONE_TIME
    assert card.tier is None
    assert card.one_time_remaining == 1


def test_one_time_card_is_limited_to_one_per_user(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    service = CardService(db_session)
    service.create_card(user.id, CardCreate(type=CardType.ONE_TIME, default_wallet_id=wallet.id))

    with pytest.raises(ConflictError):
        service.create_card(user.id, CardCreate(type=CardType.ONE_TIME, default_wallet_id=wallet.id))


def test_create_gold_credit_card(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    card = CardService(db_session).create_card(
        user.id,
        CardCreate(type=CardType.CREDIT, tier=CardTier.GOLD),
    )

    assert card.type == CardType.CREDIT
    assert card.tier == CardTier.GOLD
    assert card.default_wallet_id is None
    assert card.credit_account is not None
    assert card.credit_account.credit_limit == Decimal("15000.00")
    assert card.credit_account.used_amount == Decimal("0.00")


def test_credit_card_does_not_keep_wallet_link(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    card = CardService(db_session).create_card(
        user.id,
        CardCreate(type=CardType.CREDIT, tier=CardTier.GOLD, default_wallet_id=wallet.id),
    )

    assert card.default_wallet_id is None


def test_debit_card_rejects_duplicate_account(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    service = CardService(db_session)
    service.create_card(user.id, CardCreate(default_wallet_id=wallet.id))

    with pytest.raises(ConflictError):
        service.create_card(user.id, CardCreate(default_wallet_id=wallet.id))


def test_debit_and_one_time_cards_require_account(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    service = CardService(db_session)

    with pytest.raises(ValidationError):
        service.create_card(user.id, CardCreate())

    with pytest.raises(ValidationError):
        service.create_card(user.id, CardCreate(type=CardType.ONE_TIME))


def test_create_card_rejects_more_than_five_cards(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    service = CardService(db_session)
    for _ in range(5):
        service.create_card(user.id, CardCreate(type=CardType.CREDIT))

    with pytest.raises(ConflictError):
        service.create_card(user.id, CardCreate(type=CardType.CREDIT))


def test_one_time_card_rejects_tier(db_session, user_with_wallet):
    user, wallet = user_with_wallet

    with pytest.raises(ValidationError):
        CardService(db_session).create_card(
            user.id,
            CardCreate(type=CardType.ONE_TIME, tier=CardTier.PLATINUM, default_wallet_id=wallet.id),
        )


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
    service.create_card(other.id, CardCreate(type=CardType.CREDIT))

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
    card = CardService(db_session).create_card(other.id, CardCreate(type=CardType.CREDIT))

    with pytest.raises(NotFoundError):
        CardService(db_session).freeze_card(user.id, card.id)


def test_delete_card_removes_owned_card(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    service = CardService(db_session)
    card = service.create_card(user.id, CardCreate(default_wallet_id=wallet.id))

    service.delete_card(user.id, card.id)

    assert service.list_cards(user.id) == []
    assert CardRepository(db_session).get_preferences(card.id) is None


def test_user_cannot_delete_another_users_card(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    other = UserService(db_session).create_user(
        UserCreate(
            email="card-delete-other@example.com",
            password="Sup3rSecret!",
            first_name="Delete",
            last_name="Other",
        )
    )
    card = CardService(db_session).create_card(other.id, CardCreate(type=CardType.CREDIT))

    with pytest.raises(NotFoundError):
        CardService(db_session).delete_card(user.id, card.id)


def test_unknown_card_is_not_found(db_session, user_with_wallet):
    user, _wallet = user_with_wallet

    with pytest.raises(NotFoundError):
        CardService(db_session).get_for_user(user.id, uuid.uuid4())


def test_create_card_creates_default_payment_preferences(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    service = CardService(db_session)

    card = service.create_card(user.id, CardCreate(default_wallet_id=wallet.id))
    preferences = service.get_payment_preferences(user.id, card.id)

    assert preferences.card_id == card.id
    assert preferences.preferred_wallet_id == wallet.id
    assert preferences.allow_main_wallet_fx is False


def test_update_payment_preferences(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    service = CardService(db_session)
    card = service.create_card(user.id, CardCreate(type=CardType.CREDIT))

    preferences = service.update_payment_preferences(
        user.id,
        card.id,
        CardPaymentPreferencesUpdate(preferred_wallet_id=wallet.id, allow_main_wallet_fx=True),
    )

    assert preferences.card_id == card.id
    assert preferences.preferred_wallet_id == wallet.id
    assert preferences.allow_main_wallet_fx is True


def test_update_payment_preferences_rejects_other_users_wallet(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    other = UserService(db_session).create_user(
        UserCreate(
            email="preferences-other@example.com",
            password="Sup3rSecret!",
            first_name="Preferences",
            last_name="Other",
        )
    )
    other_wallet = WalletService(db_session).create_wallet(other.id, WalletCreate(currency="EUR"))
    card = CardService(db_session).create_card(user.id, CardCreate(type=CardType.CREDIT))

    with pytest.raises(NotFoundError):
        CardService(db_session).update_payment_preferences(
            user.id,
            card.id,
            CardPaymentPreferencesUpdate(preferred_wallet_id=other_wallet.id),
        )


def test_update_payment_preferences_rejects_frozen_wallet(db_session, user_with_wallet):
    user, wallet = user_with_wallet
    card = CardService(db_session).create_card(user.id, CardCreate(type=CardType.CREDIT))
    wallet.status = WalletStatus.FROZEN

    with pytest.raises(ValidationError):
        CardService(db_session).update_payment_preferences(
            user.id,
            card.id,
            CardPaymentPreferencesUpdate(preferred_wallet_id=wallet.id),
        )


def test_user_cannot_read_another_users_payment_preferences(db_session, user_with_wallet):
    user, _wallet = user_with_wallet
    other = UserService(db_session).create_user(
        UserCreate(
            email="preferences-security@example.com",
            password="Sup3rSecret!",
            first_name="Preferences",
            last_name="Security",
        )
    )
    card = CardService(db_session).create_card(other.id, CardCreate(type=CardType.CREDIT))

    with pytest.raises(NotFoundError):
        CardService(db_session).get_payment_preferences(user.id, card.id)
