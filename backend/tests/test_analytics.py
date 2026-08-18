from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.analytics.service import AnalyticsService
from app.core.exceptions import ValidationError
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user_with_wallet(db_session):
    user = UserService(db_session).create_user(
        UserCreate(
            email="analytics-owner@example.com",
            phone="+40745555555",
            password="Sup3rSecret!",
            first_name="Analytics",
            last_name="Owner",
        )
    )
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON"))
    db_session.flush()
    return user, wallet


def _add_transaction(db_session, user, wallet, tx_type, amount, status, created_at):
    tx = Transaction(
        initiator_user_id=user.id,
        source_wallet_id=wallet.id,
        type=tx_type,
        status=status,
        amount=Decimal(amount),
        currency="RON",
        created_at=created_at,
    )
    db_session.add(tx)
    db_session.flush()
    return tx


def test_spending_by_type_groups_and_sums_current_month(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    COMPLETED = TransactionStatus.COMPLETED
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "120.50", COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "45.00", COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.TRANSFER, "500.00", COMPLETED, now)

    result = AnalyticsService(db_session).spending_by_type(user.id, year=None, month=None)

    by_type = {item.type: item for item in result.items}
    assert by_type[TransactionType.CARD_PAYMENT].total_amount == Decimal("165.50")
    assert by_type[TransactionType.CARD_PAYMENT].transaction_count == 2
    assert by_type[TransactionType.TRANSFER].total_amount == Decimal("500.00")


def test_spending_by_type_excludes_non_completed_and_other_months(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    last_month = now.replace(day=1) - timedelta(days=1)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "999.00", TransactionStatus.FAILED, now)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "50.00", TransactionStatus.COMPLETED, last_month)

    result = AnalyticsService(db_session).spending_by_type(user.id, year=None, month=None)

    assert result.items == []


def test_spending_by_type_rejects_partial_period(db_session, seeded_user_with_wallet):
    user, _wallet = seeded_user_with_wallet

    with pytest.raises(ValidationError):
        AnalyticsService(db_session).spending_by_type(user.id, year=2026, month=None)


def _months_ago(dt: datetime, months: int) -> datetime:
    year, month = dt.year, dt.month - months
    while month <= 0:
        month += 12
        year -= 1
    return dt.replace(year=year, month=month, day=1)


def test_monthly_trend_groups_by_month_within_window(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    COMPLETED = TransactionStatus.COMPLETED
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "50.00", COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "200.00", COMPLETED, _months_ago(now, 1))
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "999.00", COMPLETED, _months_ago(now, 5))

    result = AnalyticsService(db_session).monthly_trend(user.id, months=3)

    by_month = {(item.year, item.month): item for item in result.items}
    assert by_month[(now.year, now.month)].total_amount == Decimal("150.00")
    assert by_month[(now.year, now.month)].transaction_count == 2
    prev = _months_ago(now, 1)
    assert by_month[(prev.year, prev.month)].total_amount == Decimal("200.00")
    assert (_months_ago(now, 5).year, _months_ago(now, 5).month) not in by_month


def test_monthly_trend_rejects_out_of_range_months(db_session, seeded_user_with_wallet):
    user, _wallet = seeded_user_with_wallet

    with pytest.raises(ValidationError):
        AnalyticsService(db_session).monthly_trend(user.id, months=0)

    with pytest.raises(ValidationError):
        AnalyticsService(db_session).monthly_trend(user.id, months=25)
