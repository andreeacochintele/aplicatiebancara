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
from app.wallets.models import Wallet
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


def _add_transaction(
    db_session, user, wallet, tx_type, amount, status, created_at,
    merchant_id=None, currency="RON", counterparty_user_id=None, description=None,
):
    tx = Transaction(
        initiator_user_id=user.id,
        source_wallet_id=wallet.id,
        type=tx_type,
        status=status,
        amount=Decimal(amount),
        currency=currency,
        merchant_id=merchant_id,
        counterparty_user_id=counterparty_user_id,
        description=description,
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


def test_spending_by_category_groups_by_merchant_category_not_transaction_type(db_session, seeded_user_with_wallet):
    from app.merchants.models import Merchant

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    COMPLETED = TransactionStatus.COMPLETED
    nike = Merchant(name="Nike", category="Retail", verified=True)
    starbucks = Merchant(name="Starbucks", category="Food", verified=True)
    db_session.add_all([nike, starbucks])
    db_session.flush()

    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "120.50", COMPLETED, now, merchant_id=nike.id)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "45.00", COMPLETED, now, merchant_id=nike.id)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "12.00", COMPLETED, now, merchant_id=starbucks.id)
    # Not a merchant purchase at all - must never appear in a category breakdown.
    _add_transaction(db_session, user, wallet, TransactionType.LOAN_PAYMENT, "1600.00", COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.TRANSFER, "500.00", COMPLETED, now)

    result = AnalyticsService(db_session).spending_by_category(user.id, year=None, month=None)

    by_category = {item.category: item for item in result.items}
    assert set(by_category) == {"Retail", "Food"}
    assert by_category["Retail"].total_amount == Decimal("165.50")
    assert by_category["Retail"].transaction_count == 2
    assert by_category["Food"].total_amount == Decimal("12.00")


def test_spending_by_category_groups_unmatched_merchant_as_other(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "30.00", TransactionStatus.COMPLETED, now)

    result = AnalyticsService(db_session).spending_by_category(user.id, year=None, month=None)

    assert len(result.items) == 1
    assert result.items[0].category == "Other"
    assert result.items[0].total_amount == Decimal("30.00")


def test_top_counterparties_ranks_merchants_and_transfer_recipients_together(db_session, seeded_user_with_wallet):
    from app.merchants.models import Merchant

    user, wallet = seeded_user_with_wallet
    other = UserService(db_session).create_user(
        UserCreate(email="counterparty@example.com", password="Sup3rSecret!", first_name="Ana", last_name="Pop")
    )
    now = datetime.now(timezone.utc)
    COMPLETED = TransactionStatus.COMPLETED
    nike = Merchant(name="Nike", category="Retail", verified=True)
    db_session.add(nike)
    db_session.flush()

    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "120.50", COMPLETED, now, merchant_id=nike.id)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "45.00", COMPLETED, now, merchant_id=nike.id)
    _add_transaction(
        db_session, user, wallet, TransactionType.TRANSFER, "200.00", COMPLETED, now, counterparty_user_id=other.id
    )
    # A card payment to no merchant at all falls back to the description.
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "9.00", COMPLETED, now, description="Parking meter")

    result = AnalyticsService(db_session).top_counterparties(user.id, year=None, month=None)

    by_name = {item.name: item for item in result.items}
    assert by_name["Nike"].total_amount == Decimal("165.50")
    assert by_name["Nike"].transaction_count == 2
    assert by_name["Ana Pop"].total_amount == Decimal("200.00")
    assert by_name["Parking meter"].total_amount == Decimal("9.00")
    # Highest spend first.
    assert result.items[0].name == "Ana Pop"


def test_top_counterparties_excludes_internal_transfer_and_respects_limit(db_session, user_only):
    users = UserService(db_session)
    wallets = WalletService(db_session)
    user = user_only
    ron = wallets.create_wallet(user.id, WalletCreate(currency="RON"))
    eur = wallets.create_wallet(user.id, WalletCreate(currency="EUR"))
    now = datetime.now(timezone.utc)

    # Wallet-to-wallet move between the user's own accounts - not spend at all.
    _add_transaction(db_session, user, ron, TransactionType.TRANSFER, "50.00", TransactionStatus.COMPLETED, now)
    db_session.query(Transaction).filter(Transaction.source_wallet_id == ron.id).update(
        {"destination_wallet_id": eur.id}
    )
    db_session.flush()

    names = ["Ana", "Bianca", "Cosmin"]
    for i, first_name in enumerate(names):
        other = users.create_user(
            UserCreate(email=f"vendor{i}@example.com", password="Sup3rSecret!", first_name=first_name, last_name="Vendor")
        )
        _add_transaction(
            db_session, user, ron, TransactionType.TRANSFER, f"{10 + i}.00", TransactionStatus.COMPLETED, now,
            counterparty_user_id=other.id,
        )

    result = AnalyticsService(db_session).top_counterparties(user.id, year=None, month=None, limit=2)

    assert len(result.items) == 2
    assert "Ana Vendor" not in {i.name for i in result.items}  # smallest amount (10.00), pushed out by the limit


def test_spending_recommendations_flags_week_over_week_increase(db_session, seeded_user_with_wallet):
    from app.merchants.models import Merchant

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = week_start - timedelta(days=7)
    COMPLETED = TransactionStatus.COMPLETED

    cinema = Merchant(name="Cinema City", category="Entertainment", verified=True)
    db_session.add(cinema)
    db_session.flush()

    # Last week: 100. This week: 200 (+100%, well over the 20% threshold).
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", COMPLETED, last_week_start + timedelta(days=1), merchant_id=cinema.id)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "200.00", COMPLETED, now, merchant_id=cinema.id)

    flags = AnalyticsService(db_session).spending_recommendations(user.id)

    entertainment = next(f for f in flags if f.category == "Entertainment")
    assert "WEEK_OVER_WEEK_INCREASE" in entertainment.reasons
    assert entertainment.week_over_week is not None
    assert entertainment.week_over_week.current_amount == Decimal("200.00")
    assert entertainment.week_over_week.comparison_amount == Decimal("100.00")
    assert entertainment.week_over_week.change_percent == 100.0


def test_spending_recommendations_does_not_flag_a_small_increase(db_session, seeded_user_with_wallet):
    from app.merchants.models import Merchant

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = week_start - timedelta(days=7)
    COMPLETED = TransactionStatus.COMPLETED

    zara = Merchant(name="Zara", category="Retail", verified=True)
    kfc = Merchant(name="KFC", category="Food", verified=True)
    db_session.add_all([zara, kfc])
    db_session.flush()

    # Last week: 100. This week: 105 (+5%, under the 20% threshold). A
    # second, larger category keeps Retail's month share under the
    # concentration threshold too, so only WEEK_OVER_WEEK_INCREASE is
    # actually being tested here. A steady 3-month Retail history is also
    # seeded so MONTH_VS_AVERAGE_INCREASE can't fire as a side effect of
    # "last week" occasionally falling in the previous calendar month
    # (whenever this week's Monday lands in the first few days of a month).
    for months_back in (1, 2, 3):
        _add_transaction(
            db_session, user, wallet, TransactionType.CARD_PAYMENT, "200.00", COMPLETED,
            _months_ago(datetime(now.year, now.month, 1, tzinfo=timezone.utc), months_back), merchant_id=zara.id,
        )
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", COMPLETED, last_week_start + timedelta(days=1), merchant_id=zara.id)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "105.00", COMPLETED, now, merchant_id=zara.id)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "500.00", COMPLETED, now, merchant_id=kfc.id)

    flags = AnalyticsService(db_session).spending_recommendations(user.id)

    assert not any(f.category == "Retail" for f in flags)


def test_spending_recommendations_flags_category_concentration(db_session, seeded_user_with_wallet):
    from app.merchants.models import Merchant

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    COMPLETED = TransactionStatus.COMPLETED

    petrom = Merchant(name="Petrom", category="Fuel", verified=True)
    kfc = Merchant(name="KFC", category="Food", verified=True)
    db_session.add_all([petrom, kfc])
    db_session.flush()

    # This month: Fuel 800, Food 200 -> Fuel is 80% of total, over the 40% threshold.
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "800.00", COMPLETED, now, merchant_id=petrom.id)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "200.00", COMPLETED, now, merchant_id=kfc.id)

    flags = AnalyticsService(db_session).spending_recommendations(user.id)

    fuel = next(f for f in flags if f.category == "Fuel")
    assert "CATEGORY_CONCENTRATION" in fuel.reasons
    assert fuel.share_of_total_percent == 80.0
    assert not any(f.category == "Food" for f in flags)


def test_spending_recommendations_flags_month_vs_three_month_average_increase(db_session, seeded_user_with_wallet):
    from app.merchants.models import Merchant

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    COMPLETED = TransactionStatus.COMPLETED

    booking = Merchant(name="Booking.com", category="Travel", verified=True)
    db_session.add(booking)
    db_session.flush()

    # Prior 3 months: 30 total each (avg 10/month). This month so far: 100 (+900%).
    for months_back in (1, 2, 3):
        _add_transaction(
            db_session, user, wallet, TransactionType.CARD_PAYMENT, "10.00", COMPLETED,
            _months_ago(month_start, months_back), merchant_id=booking.id,
        )
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", COMPLETED, now, merchant_id=booking.id)

    flags = AnalyticsService(db_session).spending_recommendations(user.id)

    travel = next(f for f in flags if f.category == "Travel")
    assert "MONTH_VS_AVERAGE_INCREASE" in travel.reasons
    assert travel.month_vs_three_month_average is not None
    assert travel.month_vs_three_month_average.comparison_amount == Decimal("10.00")


def test_spending_recommendations_scopes_comparisons_per_currency(db_session, seeded_user_with_wallet):
    from app.merchants.models import Merchant

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = week_start - timedelta(days=7)
    COMPLETED = TransactionStatus.COMPLETED

    emirates = Merchant(name="Emirates", category="Travel", verified=True)
    db_session.add(emirates)
    db_session.flush()

    # Last week: 1000 RON. This week: 10 USD - a currency change, not a
    # same-currency spike, must never be compared against the RON figure
    # for the week-over-week check (the USD entry is still its own
    # 100%-of-month concentration case, which is correct and separate).
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "1000.00", COMPLETED, last_week_start + timedelta(days=1), merchant_id=emirates.id, currency="RON")
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "10.00", COMPLETED, now, merchant_id=emirates.id, currency="USD")

    flags = AnalyticsService(db_session).spending_recommendations(user.id)

    usd_travel = next(f for f in flags if f.category == "Travel" and f.currency == "USD")
    assert "WEEK_OVER_WEEK_INCREASE" not in usd_travel.reasons
    assert usd_travel.week_over_week is not None
    assert usd_travel.week_over_week.comparison_amount == Decimal("0")


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


def test_monthly_trend_totals_by_month_backfills_quiet_months(db_session, seeded_user_with_wallet):
    """A brand-new account (or any account with a quiet month) must still get
    a full N-point trend line back, not a single isolated data point."""
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", TransactionStatus.COMPLETED, now)

    result = AnalyticsService(db_session).monthly_trend(user.id, months=3)

    assert len(result.totals_by_month) == 3
    by_month = {(item.year, item.month): item.total_amount for item in result.totals_by_month}
    assert by_month[(now.year, now.month)] == Decimal("100.00")
    prev = _months_ago(now, 1)
    assert by_month[(prev.year, prev.month)] == Decimal("0")
    prev2 = _months_ago(now, 2)
    assert by_month[(prev2.year, prev2.month)] == Decimal("0")
    # items (the per-currency breakdown) is intentionally NOT backfilled -
    # only totals_by_month, which is what the trend chart plots.
    assert len(result.items) == 1


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
    """WalletService.create_wallet now rejects any currency outside
    FXService's mock rate table, so this state can no longer be produced
    through normal wallet creation — the wallet below is inserted directly
    to simulate a pre-existing row (e.g. data from before that validation
    existed, or drift from a different environment) reaching net worth. That
    one wallet used to 422 net worth for every wallet the user has — it
    should just show up unconverted (rate 1) instead. Uses a fictional code
    rather than a real one so this test doesn't silently start testing the
    wrong thing if that currency is ever added to the rate table (already
    happened once — see git history)."""
    wallets = WalletService(db_session)
    ron = wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    odd = Wallet(user_id=user_only.id, currency="ZZZ")
    db_session.add(odd)
    ron.available_balance = Decimal("1000.00")
    odd.available_balance = Decimal("5000.00")
    db_session.flush()

    result = AnalyticsService(db_session).net_worth(user_only.id, base_currency=None)

    by_currency = {item.currency: item for item in result.wallets}
    assert by_currency["RON"].converted_available_balance == Decimal("1000.00")
    assert by_currency["ZZZ"].converted_available_balance == Decimal("5000.00")  # rate 1 fallback
    assert result.total_available_balance == Decimal("6000.00")


def test_net_worth_excludes_closed_wallets(db_session, user_only):
    wallets = WalletService(db_session)
    wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    eur = wallets.create_wallet(user_only.id, WalletCreate(currency="EUR"))
    wallets.close_wallet(user_only.id, eur.id)

    result = AnalyticsService(db_session).net_worth(user_only.id, base_currency=None)

    assert [item.currency for item in result.wallets] == ["RON"]


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


def test_forecast_includes_a_daily_projected_series(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    wallet.available_balance = Decimal("1000.00")
    db_session.flush()

    result = AnalyticsService(db_session).forecast_month_end_balance(user.id, wallet_id=None)

    assert len(result.projected_series) == result.days_remaining + 1
    assert result.projected_series[0].date == datetime.now(timezone.utc).date()
    assert result.projected_series[0].projected_balance == wallet.available_balance
    assert result.projected_series[-1].projected_balance == result.projected_month_end_balance


def test_spending_by_type_excludes_internal_transfer_between_own_wallets(db_session, user_only):
    wallets = WalletService(db_session)
    ron = wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    eur = wallets.create_wallet(user_only.id, WalletCreate(currency="EUR"))
    db_session.flush()
    now = datetime.now(timezone.utc)

    internal = Transaction(
        initiator_user_id=user_only.id,
        source_wallet_id=ron.id,
        destination_wallet_id=eur.id,
        type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("200.00"),
        currency="RON",
        created_at=now,
    )
    db_session.add(internal)
    db_session.flush()

    result = AnalyticsService(db_session).spending_by_type(user_only.id, year=None, month=None)

    assert result.items == []


def test_spending_by_type_still_counts_transfer_to_another_users_wallet(db_session, user_only):
    wallets = WalletService(db_session)
    other = UserService(db_session).create_user(
        UserCreate(
            email="other-transfer-recipient@example.com",
            phone="+40747777777",
            password="Sup3rSecret!",
            first_name="Other",
            last_name="User",
        )
    )
    mine = wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    theirs = wallets.create_wallet(other.id, WalletCreate(currency="RON", is_main=True))
    db_session.flush()
    now = datetime.now(timezone.utc)

    external = Transaction(
        initiator_user_id=user_only.id,
        source_wallet_id=mine.id,
        destination_wallet_id=theirs.id,
        counterparty_user_id=other.id,
        type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("75.00"),
        currency="RON",
        created_at=now,
    )
    db_session.add(external)
    db_session.flush()

    result = AnalyticsService(db_session).spending_by_type(user_only.id, year=None, month=None)

    assert result.items[0].total_amount == Decimal("75.00")


def test_spending_by_type_excludes_cashback(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "40.00", TransactionStatus.COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.CASHBACK, "5.00", TransactionStatus.COMPLETED, now)

    result = AnalyticsService(db_session).spending_by_type(user.id, year=None, month=None)

    by_type = {item.type: item for item in result.items}
    assert TransactionType.CASHBACK not in by_type
    assert by_type[TransactionType.CARD_PAYMENT].total_amount == Decimal("40.00")


def test_spending_by_type_excludes_loan_payment(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "40.00", TransactionStatus.COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.LOAN_PAYMENT, "1600.00", TransactionStatus.COMPLETED, now)

    result = AnalyticsService(db_session).spending_by_type(user.id, year=None, month=None)

    by_type = {item.type: item for item in result.items}
    assert TransactionType.LOAN_PAYMENT not in by_type
    assert by_type[TransactionType.CARD_PAYMENT].total_amount == Decimal("40.00")


def test_spending_by_type_excludes_top_up(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "40.00", TransactionStatus.COMPLETED, now)
    _add_transaction(db_session, user, wallet, TransactionType.TOP_UP, "500.00", TransactionStatus.COMPLETED, now)

    result = AnalyticsService(db_session).spending_by_type(user.id, year=None, month=None)

    by_type = {item.type: item for item in result.items}
    assert TransactionType.TOP_UP not in by_type
    assert by_type[TransactionType.CARD_PAYMENT].total_amount == Decimal("40.00")


def test_monthly_trend_converts_totals_to_base_currency(db_session, user_only):
    wallets = WalletService(db_session)
    ron = wallets.create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    eur = wallets.create_wallet(user_only.id, WalletCreate(currency="EUR"))
    db_session.flush()
    now = datetime.now(timezone.utc)
    _add_transaction(db_session, user_only, ron, TransactionType.CARD_PAYMENT, "100.00", TransactionStatus.COMPLETED, now)
    _add_transaction(db_session, user_only, eur, TransactionType.CARD_PAYMENT, "10.00", TransactionStatus.COMPLETED, now)

    result = AnalyticsService(db_session).monthly_trend(user_only.id, months=1)

    assert result.base_currency == "RON"
    assert len(result.totals_by_month) == 1
    total = result.totals_by_month[0]
    assert total.year == now.year and total.month == now.month
    # 100 RON + 10 EUR converted at the mock FX rate (RON/EUR ~= 4.97, see FXService)
    assert total.total_amount > Decimal("100.00")


def test_net_worth_history_reconstructs_daily_balances_from_ledger(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    three_days_ago = now - timedelta(days=3)
    wallet.created_at = three_days_ago - timedelta(days=5)
    wallet.available_balance = Decimal("300.00")
    db_session.flush()
    tx = _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", TransactionStatus.COMPLETED, three_days_ago)
    entry = WalletLedgerEntry(
        wallet_id=wallet.id,
        transaction_id=tx.id,
        entry_type=LedgerEntryType.DEBIT,
        amount=Decimal("100.00"),
        currency=wallet.currency,
        balance_after=Decimal("300.00"),
        created_at=three_days_ago,
    )
    db_session.add(entry)
    db_session.flush()

    result = AnalyticsService(db_session).net_worth_history(user.id, period="3m", base_currency=None)

    assert result.base_currency == "RON"
    by_date = {point.date: point.value for point in result.history}
    assert by_date[now.date()] == Decimal("300.00")
    day_before_debit = (three_days_ago - timedelta(days=1)).date()
    assert by_date[day_before_debit] == Decimal("400.00")


def test_net_worth_history_rejects_unknown_period(db_session, user_only):
    with pytest.raises(ValidationError):
        AnalyticsService(db_session).net_worth_history(user_only.id, period="bogus", base_currency=None)


def test_balance_history_reconstructs_a_range_ending_before_today(db_session, seeded_user_with_wallet):
    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    five_days_ago = now - timedelta(days=5)
    wallet.created_at = five_days_ago - timedelta(days=5)
    wallet.available_balance = Decimal("300.00")
    db_session.flush()
    tx = _add_transaction(db_session, user, wallet, TransactionType.CARD_PAYMENT, "100.00", TransactionStatus.COMPLETED, five_days_ago)
    entry = WalletLedgerEntry(
        wallet_id=wallet.id,
        transaction_id=tx.id,
        entry_type=LedgerEntryType.DEBIT,
        amount=Decimal("100.00"),
        currency=wallet.currency,
        balance_after=Decimal("300.00"),
        created_at=five_days_ago,
    )
    db_session.add(entry)
    db_session.flush()

    result = AnalyticsService(db_session).wallet_balance_history(
        user.id,
        wallet_id=None,
        date_from=(five_days_ago - timedelta(days=2)).date(),
        date_to=five_days_ago.date(),
    )

    assert result.currency == "RON"
    dates = [point.date for point in result.history]
    # date_to is before today: today must not leak into a bounded historical range.
    assert now.date() not in dates
    assert dates[-1] == five_days_ago.date()
    by_date = {point.date: point.balance for point in result.history}
    assert by_date[five_days_ago.date()] == Decimal("300.00")
    day_before_debit = (five_days_ago - timedelta(days=1)).date()
    assert by_date[day_before_debit] == Decimal("400.00")


def test_balance_history_rejects_date_from_after_date_to(db_session, seeded_user_with_wallet):
    user, _wallet = seeded_user_with_wallet
    today = datetime.now(timezone.utc).date()
    with pytest.raises(ValidationError):
        AnalyticsService(db_session).wallet_balance_history(
            user.id, wallet_id=None, date_from=today, date_to=today - timedelta(days=1)
        )


def test_balance_history_raises_not_found_for_unknown_wallet(db_session, user_only):
    WalletService(db_session).create_wallet(user_only.id, WalletCreate(currency="RON", is_main=True))
    db_session.flush()
    today = datetime.now(timezone.utc).date()
    with pytest.raises(NotFoundError):
        AnalyticsService(db_session).wallet_balance_history(
            user_only.id, wallet_id=uuid.uuid4(), date_from=today - timedelta(days=1), date_to=today
        )


# ---- per-transaction category override. The user re-files one payment from
# the Transactions page; the donut and Budgets both resolve through
# transactions/categories.py, so both must move together.


def test_spending_by_category_prefers_the_users_own_category_over_the_merchants(
    db_session, seeded_user_with_wallet
):
    from app.merchants.models import Merchant
    from app.transactions.models import TransactionCategory

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    cinema = Merchant(name="Cinema City", category="Entertainment", verified=True)
    food = TransactionCategory(name="Food")
    db_session.add_all([cinema, food])
    db_session.flush()

    _add_transaction(
        db_session, user, wallet, TransactionType.CARD_PAYMENT, "50.00",
        TransactionStatus.COMPLETED, now, merchant_id=cinema.id,
    )
    kept = _add_transaction(
        db_session, user, wallet, TransactionType.CARD_PAYMENT, "30.00",
        TransactionStatus.COMPLETED, now, merchant_id=cinema.id,
    )

    before = {i.category: i.total_amount for i in AnalyticsService(db_session).spending_by_category(user.id, None, None).items}
    assert before == {"Entertainment": Decimal("80.00")}

    # Re-file only the 50.00 one.
    moved = db_session.query(Transaction).filter(Transaction.amount == Decimal("50.00")).one()
    moved.category_id = food.id
    db_session.flush()

    after = {i.category: i.total_amount for i in AnalyticsService(db_session).spending_by_category(user.id, None, None).items}
    assert after == {"Entertainment": Decimal("30.00"), "Food": Decimal("50.00")}
    assert kept.category_id is None  # untouched


def test_spending_by_category_falls_back_to_the_merchant_when_the_override_is_cleared(
    db_session, seeded_user_with_wallet
):
    from app.merchants.models import Merchant
    from app.transactions.models import TransactionCategory

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    cinema = Merchant(name="Cinema City", category="Entertainment", verified=True)
    food = TransactionCategory(name="Food")
    db_session.add_all([cinema, food])
    db_session.flush()
    tx = _add_transaction(
        db_session, user, wallet, TransactionType.CARD_PAYMENT, "50.00",
        TransactionStatus.COMPLETED, now, merchant_id=cinema.id,
    )
    tx.category_id = food.id
    db_session.flush()

    tx.category_id = None
    db_session.flush()

    result = AnalyticsService(db_session).spending_by_category(user.id, None, None)
    assert {i.category: i.total_amount for i in result.items} == {"Entertainment": Decimal("50.00")}


def test_a_recategorised_payment_moves_between_budgets_too(db_session, seeded_user_with_wallet):
    """The whole point of resolving in one place: Analytics and Budgets can
    never report different spend for the same category and month."""
    from app.budgets.repository import BudgetRepository
    from app.merchants.models import Merchant
    from app.transactions.models import TransactionCategory

    user, wallet = seeded_user_with_wallet
    now = datetime.now(timezone.utc)
    cinema = Merchant(name="Cinema City", category="Entertainment", verified=True)
    food = TransactionCategory(name="Food")
    db_session.add_all([cinema, food])
    db_session.flush()
    tx = _add_transaction(
        db_session, user, wallet, TransactionType.CARD_PAYMENT, "50.00",
        TransactionStatus.COMPLETED, now, merchant_id=cinema.id,
    )
    period_start, period_end = now - timedelta(days=1), now + timedelta(days=1)
    budgets = BudgetRepository(db_session)

    assert budgets.spent_amount(user.id, "Entertainment", "RON", period_start, period_end) == Decimal("50.00")
    assert budgets.spent_amount(user.id, "Food", "RON", period_start, period_end) == Decimal("0")

    tx.category_id = food.id
    db_session.flush()

    assert budgets.spent_amount(user.id, "Entertainment", "RON", period_start, period_end) == Decimal("0")
    assert budgets.spent_amount(user.id, "Food", "RON", period_start, period_end) == Decimal("50.00")
