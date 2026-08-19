from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.cards.models import CardTier
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import NotFoundError, ValidationError
from app.merchants.schemas import CashbackOfferCreate, MerchantCreate
from app.merchants.service import MerchantService
from app.rewards.service import RewardsService
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="merchant-user@example.com", password="Sup3rSecret!", first_name="Merch", last_name="User")
    )


def _active_offer_window() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=1), today + timedelta(days=30)


def _card_payment(
    db_session, user_id, amount, description, status=TransactionStatus.COMPLETED, card_id=None
) -> Transaction:
    transaction = Transaction(
        initiator_user_id=user_id,
        type=TransactionType.CARD_PAYMENT,
        status=status,
        amount=amount,
        currency="RON",
        description=description,
        card_id=card_id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction


def test_list_merchants_only_returns_active(db_session):
    from app.merchants.models import MerchantStatus

    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="Nike", category="Retail"))
    inactive = service.create_merchant(MerchantCreate(name="Old Shop", category="Retail"))

    merchant_row = service.repository.get_by_id(inactive.id)
    merchant_row.status = MerchantStatus.INACTIVE
    db_session.flush()

    merchants = service.list_merchants()

    assert {m.name for m in merchants} == {"Nike"}


def test_create_cashback_offer_rejects_non_positive_percent(db_session):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Nike", category="Retail"))
    start, end = _active_offer_window()

    with pytest.raises(ValidationError):
        service.create_cashback_offer(
            merchant.id,
            CashbackOfferCreate(cashback_percent=Decimal("0"), start_date=start, end_date=end),
        )


def test_create_cashback_offer_for_unknown_merchant_raises_not_found(db_session):
    import uuid

    service = MerchantService(db_session)
    start, end = _active_offer_window()

    with pytest.raises(NotFoundError):
        service.create_cashback_offer(
            uuid.uuid4(),
            CashbackOfferCreate(cashback_percent=Decimal("7"), start_date=start, end_date=end),
        )


def test_sync_awards_points_and_computes_cashback_from_real_transaction(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(cashback_percent=Decimal("7"), start_date=start, end_date=end),
    )
    _card_payment(db_session, seeded_user.id, Decimal("400.00"), "Nike - Shopping")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert len(results) == 1
    result = results[0]
    assert result.points_earned == 400
    assert result.cashback_percent == Decimal("7")
    assert result.cashback_amount == Decimal("28.00")
    assert result.reward_points_balance == 400

    rewards_account = RewardsService(db_session).get_account(seeded_user.id)
    assert rewards_account.points_balance == 400


def test_sync_scales_points_by_card_tier(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    card = CardService(db_session).create_card(seeded_user.id, CardCreate(tier=CardTier.GOLD))
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Nike - Shopping", card_id=card.id)

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].points_earned == 400  # 200 RON * 2x (GOLD)


def test_sync_platinum_card_doubles_points(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    card = CardService(db_session).create_card(seeded_user.id, CardCreate(tier=CardTier.PLATINUM))
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Nike - Shopping", card_id=card.id)

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].points_earned == 600  # 200 RON * 3x (PLATINUM)


def test_sync_without_a_known_card_uses_base_rate(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Nike - Shopping")  # no card_id, e.g. seed data

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].points_earned == 200


def test_sync_caps_cashback_at_maximum(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Starbucks", category="Food", verified=True))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(
            cashback_percent=Decimal("10"), maximum_cashback=Decimal("5.00"), start_date=start, end_date=end
        ),
    )
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Starbucks - Coffee")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].cashback_amount == Decimal("5.00")


def test_sync_below_minimum_spend_earns_no_cashback(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="eMAG", category="Retail", verified=True))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(cashback_percent=Decimal("5"), minimum_spend=Decimal("100.00"), start_date=start, end_date=end),
    )
    _card_payment(db_session, seeded_user.id, Decimal("50.00"), "eMAG order")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].cashback_percent is None
    assert results[0].cashback_amount == Decimal("0")
    assert results[0].points_earned == 50


def test_sync_ignores_unverified_merchants(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel"))  # verified defaults to False
    _card_payment(db_session, seeded_user.id, Decimal("120.00"), "OMV - Fuel")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []
    assert RewardsService(db_session).get_account(seeded_user.id).points_balance == 0


def test_sync_ignores_transactions_at_unknown_merchants(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel"))
    _card_payment(db_session, seeded_user.id, Decimal("120.00"), "Unlisted Shop")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []


def test_sync_ignores_non_completed_or_non_card_transactions(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel"))
    _card_payment(db_session, seeded_user.id, Decimal("100.00"), "OMV - Fuel", status=TransactionStatus.PENDING_REVIEW)
    pending = Transaction(
        initiator_user_id=seeded_user.id,
        type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("100.00"),
        currency="RON",
        description="OMV - Fuel",
    )
    db_session.add(pending)
    db_session.flush()

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []


def test_sync_does_not_double_award_the_same_transaction(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel", verified=True))
    _card_payment(db_session, seeded_user.id, Decimal("100.00"), "OMV - Fuel")

    first = service.sync_purchases_from_transactions(seeded_user.id)
    second = service.sync_purchases_from_transactions(seeded_user.id)

    assert len(first) == 1
    assert second == []
    assert RewardsService(db_session).get_account(seeded_user.id).points_balance == 100


def test_sync_survives_a_concurrent_award_race(db_session, seeded_user, monkeypatch):
    """Simulates two overlapping sync calls both passing the has_earned_for_transaction
    check before either commits — the unique constraint (migration 0011) plus the
    per-row savepoint should make the loser skip that transaction instead of
    crashing the whole sync call or double-crediting points."""
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel", verified=True))
    payment = _card_payment(db_session, seeded_user.id, Decimal("100.00"), "OMV - Fuel")

    # A "concurrent" request already committed its award for this transaction...
    RewardsService(db_session).earn_points(
        seeded_user.id, 100, description="Card payment at OMV", source_transaction_id=payment.id
    )
    # ...but pretend our check ran before that commit was visible, so this call
    # still attempts to insert a second reward_transaction for the same payment.
    monkeypatch.setattr(RewardsService, "has_earned_for_transaction", lambda self, source_transaction_id: False)

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []
    assert RewardsService(db_session).get_account(seeded_user.id).points_balance == 100
