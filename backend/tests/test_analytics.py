import calendar
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.analytics.service import AnalyticsService
from app.core.exceptions import NotFoundError, ValidationError
from app.transactions.models import (
    LedgerEntryType,
    Transaction,
    TransactionStatus,
    TransactionType,
    WalletLedgerEntry,
)
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def user_only(db_session):
    return UserService(db_session).create_user(
        UserCreate(
            email="net-worth-owner@example.com",
            phone="+40746666666",
            password="Sup3rSecret!",
            first_name="Net",
            last_name="Worth",
        )
    )


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


def _add_ledger_entry(db_session, wallet, transaction, entry_type, amount, created_at):
    entry = WalletLedgerEntry(
        wallet_id=wallet.id,
        transaction_id=transaction.id,
        entry_type=entry_type,
        amount=Decimal(amount),
        currency=wallet.currency,
        balance_after=Decimal("0"),
        created_at=created_at,
    )
    db_session.add(entry)
    db_session.flush()
    return entry


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


def test_net_worth_converts_and_sums_multi_currency_wallets(db_session, user_only):
    wallets = WalletService(db_session)
    ron = wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    eur = wallets.create_wallet(user_only.id, WalletCreate(currency="EUR"))
    ron.available_balance = Decimal("1000.00")
    eur.available_balance = Decimal("100.00")
    db_session.flush()

    result = AnalyticsService(db_session).net_worth(user_only.id, base_currency=None)

    assert result.base_currency == "RON"
    assert result.total_available_balance == Decimal("1497.00")
    by_currency = {item.currency: item for item in result.wallets}
    assert by_currency["RON"].converted_available_balance == Decimal("1000.00")
    assert by_currency["EUR"].converted_available_balance == Decimal("497.00")


def test_net_worth_defaults_base_currency_to_main_wallet(db_session, user_only):
    wallets = WalletService(db_session)
    wallets.create_wallet(user_only.id, WalletCreate(currency="EUR", is_main=True))
    db_session.flush()

    result = AnalyticsService(db_session).net_worth(user_only.id, base_currency=None)

    assert result.base_currency == "EUR"


def test_net_worth_with_no_wallets_returns_zero(db_session, user_only):
    result = AnalyticsService(db_session).net_worth(user_only.id, base_currency=None)

    assert result.base_currency == "RON"
    assert result.total_available_balance == Decimal("0")
    assert result.wallets == []


def test_net_worth_survives_a_wallet_in_an_unsupported_currency(db_session, user_only):
    """Nothing validates wallet currency against FXService's mock rate table
    at wallet-creation time, so a wallet in e.g. JPY is possible. That one
    wallet used to 422 net worth for every wallet the user has — it should
    just show up unconverted (rate 1) instead."""
    wallets = WalletService(db_session)
    ron = wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    odd = wallets.create_wallet(user_only.id, WalletCreate(currency="JPY"))
    ron.available_balance = Decimal("1000.00")
    odd.available_balance = Decimal("5000.00")
    db_session.flush()

    result = AnalyticsService(db_session).net_worth(user_only.id, base_currency=None)

    by_currency = {item.currency: item for item in result.wallets}
    assert by_currency["RON"].converted_available_balance == Decimal("1000.00")
    assert by_currency["JPY"].converted_available_balance == Decimal("5000.00")  # rate 1 fallback
    assert result.total_available_balance == Decimal("6000.00")


def test_forecast_projects_from_net_ledger_change(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    wallet.available_balance = Decimal("1000.00")
    db_session.flush()
    now = datetime.now(timezone.utc)
    tx = _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", TransactionStatus.COMPLETED, now)
    _add_ledger_entry(db_session, wallet, tx, LedgerEntryType.DEBIT, "100.00", now)
    _add_ledger_entry(db_session, wallet, tx, LedgerEntryType.CREDIT, "50.00", now)

    result = AnalyticsService(db_session).forecast_month_end_balance(user.id, wallet_id=None)

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_elapsed = (now.date() - month_start.date()).days + 1
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_remaining = days_in_month - days_elapsed
    expected_avg = ((Decimal("50.00") - Decimal("100.00")) / days_elapsed).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    expected_change = (expected_avg * days_remaining).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    assert result.wallet_id == wallet.id
    assert result.days_elapsed == days_elapsed
    assert result.days_remaining == days_remaining
    assert result.average_daily_net_change == expected_avg
    assert result.projected_month_end_balance == wallet.available_balance + expected_change


def test_forecast_ignores_hold_and_release_entries(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    wallet.available_balance = Decimal("500.00")
    db_session.flush()
    now = datetime.now(timezone.utc)
    tx = _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "1.00", TransactionStatus.PENDING_REVIEW, now)
    _add_ledger_entry(db_session, wallet, tx, LedgerEntryType.HOLD, "12000.00", now)
    _add_ledger_entry(db_session, wallet, tx, LedgerEntryType.RELEASE, "12000.00", now)

    result = AnalyticsService(db_session).forecast_month_end_balance(user.id, wallet_id=None)

    assert result.average_daily_net_change == Decimal("0.00")
    assert result.projected_month_end_balance == wallet.available_balance


def test_forecast_defaults_to_main_wallet(db_session, user_only):
    wallets = WalletService(db_session)
    ron = wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    wallets.create_wallet(user_only.id, WalletCreate(currency="EUR"))
    db_session.flush()

    result = AnalyticsService(db_session).forecast_month_end_balance(user_only.id, wallet_id=None)

    assert result.wallet_id == ron.id
    assert result.currency == "RON"


def test_forecast_raises_not_found_for_no_wallets_or_unknown_wallet(db_session, user_only):
    with pytest.raises(NotFoundError):
        AnalyticsService(db_session).forecast_month_end_balance(user_only.id, wallet_id=None)

    WalletService(db_session).create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    db_session.flush()

    with pytest.raises(NotFoundError):
        AnalyticsService(db_session).forecast_month_end_balance(user_only.id, wallet_id=uuid.uuid4())
