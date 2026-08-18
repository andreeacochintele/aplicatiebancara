from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.merchants.schemas import CashbackOfferCreate, MerchantCreate, PurchaseCreate
from app.merchants.service import MerchantService
from app.rewards.service import RewardsService
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


def test_record_purchase_awards_points_and_computes_cashback(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Nike", category="Retail"))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(cashback_percent=Decimal("7"), start_date=start, end_date=end),
    )

    result = service.record_purchase(seeded_user.id, merchant.id, PurchaseCreate(amount=Decimal("400.00")))

    assert result.points_earned == 400
    assert result.cashback_percent == Decimal("7")
    assert result.cashback_amount == Decimal("28.00")
    assert result.reward_points_balance == 400

    rewards_account = RewardsService(db_session).get_account(seeded_user.id)
    assert rewards_account.points_balance == 400


def test_record_purchase_caps_cashback_at_maximum(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Starbucks", category="Food"))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(
            cashback_percent=Decimal("10"), maximum_cashback=Decimal("5.00"), start_date=start, end_date=end
        ),
    )

    result = service.record_purchase(seeded_user.id, merchant.id, PurchaseCreate(amount=Decimal("200.00")))

    assert result.cashback_amount == Decimal("5.00")


def test_record_purchase_below_minimum_spend_earns_no_cashback(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="eMAG", category="Retail"))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(cashback_percent=Decimal("5"), minimum_spend=Decimal("100.00"), start_date=start, end_date=end),
    )

    result = service.record_purchase(seeded_user.id, merchant.id, PurchaseCreate(amount=Decimal("50.00")))

    assert result.cashback_percent is None
    assert result.cashback_amount == Decimal("0")
    assert result.points_earned == 50


def test_record_purchase_rejects_non_positive_amount(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="OMV", category="Fuel"))

    with pytest.raises(ValidationError):
        service.record_purchase(seeded_user.id, merchant.id, PurchaseCreate(amount=Decimal("0")))


def test_record_purchase_for_unknown_merchant_raises_not_found(db_session, seeded_user):
    import uuid

    service = MerchantService(db_session)
    with pytest.raises(NotFoundError):
        service.record_purchase(seeded_user.id, uuid.uuid4(), PurchaseCreate(amount=Decimal("10.00")))
