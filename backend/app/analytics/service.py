"""Analytics business rules: read-only aggregates over the transaction and wallet data
other modules own. Currency conversion is delegated to FXService (fx/service.py) rather
than re-deriving rates here — analytics only aggregates, it never prices FX itself."""
import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.analytics.repository import AnalyticsRepository
from app.analytics.schemas import (
    BalanceHistoryPoint,
    BalanceHistoryResponse,
    CategorySpendingFlag,
    CounterpartySpending,
    ForecastPoint,
    ForecastResponse,
    MonthlyTrendItem,
    MonthlyTrendResponse,
    MonthlyTrendTotal,
    NetWorthHistoryPoint,
    NetWorthHistoryResponse,
    NetWorthResponse,
    SpendingByCategory,
    SpendingByCategoryResponse,
    SpendingByType,
    SpendingByTypeResponse,
    SpendingComparisonPoint,
    TopCounterpartiesResponse,
    WalletBalanceItem,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.fx.service import FXService
from app.merchants.repository import MerchantRepository
from app.users.repository import UserRepository
from app.wallets.models import Wallet, WalletStatus
from app.wallets.repository import WalletRepository

_FORECAST_NOTE = (
    "Simplified projection based on this month's ledger trend only — does not "
    "yet account for scheduled payments or loan instalments."
)

_NET_WORTH_HISTORY_NOTE = (
    "Historical balances are reconstructed from the wallet ledger; conversions to "
    "the base currency use today's FX rate throughout, not the rate on each date."
)

def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) silently drops tzinfo on DateTime(timezone=True)
    columns on read-back, while Postgres (production) preserves it — normalize
    here so window comparisons below never mix naive and aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


_BALANCE_HISTORY_NOTE = (
    "Actual balance reconstructed from the wallet ledger for the selected range — not a projection."
)

_HISTORY_PERIOD_DAYS = {"3m": 90, "6m": 182, "1y": 365}

_CENTS = Decimal("0.01")

# Thresholds for spending_recommendations() — deliberately visible/tunable
# constants, not derived from any real usage data. Defaults match the
# examples given when this feature was scoped.
SPENDING_INCREASE_THRESHOLD_PERCENT = Decimal("20")
CATEGORY_CONCENTRATION_THRESHOLD_PERCENT = Decimal("40")


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AnalyticsRepository(db)
        self.wallet_repository = WalletRepository(db)
        self.fx_service = FXService(db)
        self.merchants = MerchantRepository(db)
        self.users = UserRepository(db)

    def _month_period_bounds(self, year: int | None, month: int | None) -> tuple[datetime, datetime]:
        if (year is None) != (month is None):
            raise ValidationError("year and month must be provided together")

        now = datetime.now(timezone.utc)
        year = year or now.year
        month = month or now.month
        if not 1 <= month <= 12:
            raise ValidationError("month must be between 1 and 12")

        period_start = datetime(year, month, 1, tzinfo=timezone.utc)
        days_in_month = calendar.monthrange(year, month)[1]
        period_end = datetime(year, month, days_in_month, 23, 59, 59, 999999, tzinfo=timezone.utc)
        return period_start, period_end

    def spending_by_type(self, user_id: uuid.UUID, year: int | None, month: int | None) -> SpendingByTypeResponse:
        period_start, period_end = self._month_period_bounds(year, month)

        rows = self.repository.spending_by_type(user_id, period_start, period_end)
        items = [
            SpendingByType(type=tx_type, total_amount=total, currency=currency, transaction_count=count)
            for tx_type, currency, total, count in rows
        ]
        return SpendingByTypeResponse(
            period_start=period_start.date(), period_end=period_end.date(), items=items
        )

    def spending_by_category(
        self, user_id: uuid.UUID, year: int | None, month: int | None
    ) -> SpendingByCategoryResponse:
        period_start, period_end = self._month_period_bounds(year, month)

        rows = self.repository.spending_by_merchant_category(user_id, period_start, period_end)
        items = [
            SpendingByCategory(category=category, total_amount=total, currency=currency, transaction_count=count)
            for category, currency, total, count in rows
        ]
        return SpendingByCategoryResponse(
            period_start=period_start.date(), period_end=period_end.date(), items=items
        )

    def top_counterparties(
        self, user_id: uuid.UUID, year: int | None, month: int | None, limit: int = 10
    ) -> TopCounterpartiesResponse:
        period_start, period_end = self._month_period_bounds(year, month)
        transactions = self.repository.spend_transactions_for_counterparties(user_id, period_start, period_end)

        name_cache: dict[tuple[str, uuid.UUID], str] = {}
        totals: dict[tuple[str, str], dict[str, object]] = {}
        for transaction in transactions:
            name = self._resolve_counterparty_name(transaction, name_cache)
            if not name:
                continue
            key = (name, transaction.currency)
            bucket = totals.setdefault(key, {"total": Decimal("0"), "count": 0})
            bucket["total"] += transaction.amount
            bucket["count"] += 1

        items = sorted(
            (
                CounterpartySpending(name=name, currency=currency, total_amount=b["total"], transaction_count=b["count"])
                for (name, currency), b in totals.items()
            ),
            key=lambda item: item.total_amount,
            reverse=True,
        )[:limit]
        return TopCounterpartiesResponse(period_start=period_start.date(), period_end=period_end.date(), items=items)

    def _resolve_counterparty_name(self, transaction, cache: dict[tuple[str, uuid.UUID], str]) -> str:
        """Same resolution order as exports/service.py's _resolve_counterparty
        (merchant first, then a counterparty user, else unnamed) — kept as
        its own small copy rather than a shared import since the two callers
        sit in different modules with no natural owner for a shared helper
        this size."""
        if transaction.merchant_id is not None:
            key = ("merchant", transaction.merchant_id)
            if key not in cache:
                merchant = self.merchants.get_by_id(transaction.merchant_id)
                cache[key] = merchant.name if merchant is not None else ""
            return cache[key]
        if transaction.counterparty_user_id is not None:
            key = ("user", transaction.counterparty_user_id)
            if key not in cache:
                counterparty = self.users.get_by_id(transaction.counterparty_user_id)
                cache[key] = f"{counterparty.first_name} {counterparty.last_name}" if counterparty is not None else ""
            return cache[key]
        return (transaction.description or "")[:60]

    def spending_recommendations(self, user_id: uuid.UUID) -> list[CategorySpendingFlag]:
        """Pure calculation, no AI — see ai/personal_finance/insights.py for
        the LLM phrasing layer that consumes this list. A category is
        flagged when any comparison below crosses its threshold:

        - week-over-week: this week's spend in a category vs last week's,
          up more than SPENDING_INCREASE_THRESHOLD_PERCENT.
        - month-vs-3m-average: this month's spend (month-to-date) in a
          category vs that category's own average over the prior 3
          complete calendar months, up more than
          SPENDING_INCREASE_THRESHOLD_PERCENT.
        - concentration: one category is more than
          CATEGORY_CONCENTRATION_THRESHOLD_PERCENT of this month's total
          spend across all categories (same currency).

        All three are scoped per currency — a category's RON spend is
        never compared against or blended with its USD spend, same
        convention spending_by_category()'s donut view already uses.
        Only flagged categories are returned; a quiet category (nothing
        crossed a threshold) doesn't appear in the result at all.
        """
        now = datetime.now(timezone.utc)

        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        last_week_start = week_start - timedelta(days=7)

        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        three_months_start = self._months_before(month_start, 3)

        this_week = self._category_totals(user_id, week_start, now)
        last_week = self._category_totals(user_id, last_week_start, week_start)
        this_month = self._category_totals(user_id, month_start, now)
        prior_three_months = self._category_totals(user_id, three_months_start, month_start)

        this_month_total_by_currency: dict[str, Decimal] = {}
        for (_category, currency), amount in this_month.items():
            this_month_total_by_currency[currency] = this_month_total_by_currency.get(currency, Decimal("0")) + amount

        flags: list[CategorySpendingFlag] = []
        for category, currency in sorted(set(this_week) | set(this_month)):
            reasons: list[str] = []

            week_point = None
            current_week_amount = this_week.get((category, currency), Decimal("0"))
            prior_week_amount = last_week.get((category, currency), Decimal("0"))
            if current_week_amount > 0 or prior_week_amount > 0:
                change = self._percent_change(prior_week_amount, current_week_amount)
                week_point = SpendingComparisonPoint(
                    current_amount=current_week_amount, comparison_amount=prior_week_amount, change_percent=change
                )
                if change is not None and change > float(SPENDING_INCREASE_THRESHOLD_PERCENT):
                    reasons.append("WEEK_OVER_WEEK_INCREASE")

            month_point = None
            current_month_amount = this_month.get((category, currency), Decimal("0"))
            avg_prior_amount = (prior_three_months.get((category, currency), Decimal("0")) / Decimal("3")).quantize(
                _CENTS
            )
            if current_month_amount > 0 or avg_prior_amount > 0:
                change = self._percent_change(avg_prior_amount, current_month_amount)
                month_point = SpendingComparisonPoint(
                    current_amount=current_month_amount, comparison_amount=avg_prior_amount, change_percent=change
                )
                if change is not None and change > float(SPENDING_INCREASE_THRESHOLD_PERCENT):
                    reasons.append("MONTH_VS_AVERAGE_INCREASE")

            share_percent = None
            month_total = this_month_total_by_currency.get(currency, Decimal("0"))
            if month_total > 0 and current_month_amount > 0:
                share_percent = round(float((current_month_amount / month_total) * 100), 1)
                if share_percent > float(CATEGORY_CONCENTRATION_THRESHOLD_PERCENT):
                    reasons.append("CATEGORY_CONCENTRATION")

            if reasons:
                flags.append(
                    CategorySpendingFlag(
                        category=category,
                        currency=currency,
                        reasons=reasons,
                        week_over_week=week_point,
                        month_vs_three_month_average=month_point,
                        share_of_total_percent=share_percent,
                    )
                )
        return flags

    def _category_totals(
        self, user_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> dict[tuple[str, str], Decimal]:
        rows = self.repository.spending_by_merchant_category(user_id, period_start, period_end)
        return {(category, currency): total for category, currency, total, _count in rows}

    @staticmethod
    def _percent_change(before: Decimal, after: Decimal) -> float | None:
        if before <= 0:
            return None
        return float(((after - before) / before) * 100)

    @staticmethod
    def _months_before(dt: datetime, months: int) -> datetime:
        month_index = dt.month - 1 - months
        year = dt.year + month_index // 12
        month = month_index % 12 + 1
        return dt.replace(year=year, month=month)

    def monthly_trend(
        self, user_id: uuid.UUID, months: int, base_currency: str | None = None
    ) -> MonthlyTrendResponse:
        if not 1 <= months <= 24:
            raise ValidationError("months must be between 1 and 24")

        wallets = [w for w in self.wallet_repository.list_for_user(user_id) if w.status != WalletStatus.CLOSED]
        base = self._resolve_base_currency(wallets, base_currency)

        now = datetime.now(timezone.utc)
        start_year, start_month = now.year, now.month - (months - 1)
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        period_start = datetime(start_year, start_month, 1, tzinfo=timezone.utc)

        rows = self.repository.completed_transactions_in_range(user_id, period_start, now)

        # Grouped in Python rather than a SQL date-trunc: keeps the query portable
        # across the Postgres (prod) and SQLite (tests) dialects the app targets.
        buckets: dict[tuple[int, int, str], dict[str, object]] = {}
        for amount, currency, created_at in rows:
            key = (created_at.year, created_at.month, currency)
            bucket = buckets.setdefault(key, {"total": Decimal("0"), "count": 0})
            bucket["total"] += amount
            bucket["count"] += 1

        items = [
            MonthlyTrendItem(year=year, month=month, currency=currency, total_amount=b["total"], transaction_count=b["count"])
            for (year, month, currency), b in sorted(buckets.items())
        ]

        totals_by_month: dict[tuple[int, int], Decimal] = {}
        for (year, month, currency), b in buckets.items():
            converted = (b["total"] * self._rate_to(currency, base)).quantize(_CENTS, rounding=ROUND_HALF_UP)
            totals_by_month[(year, month)] = totals_by_month.get((year, month), Decimal("0")) + converted

        # Backfilled with a zero entry for every month in the requested
        # window that had no activity at all, not just the months that
        # actually had a transaction — a brand-new account (or any account
        # with a quiet month) would otherwise get back a single isolated
        # data point instead of a real "last N months" trend line.
        cursor_year, cursor_month = start_year, start_month
        for _ in range(months):
            totals_by_month.setdefault((cursor_year, cursor_month), Decimal("0"))
            cursor_month += 1
            if cursor_month > 12:
                cursor_month = 1
                cursor_year += 1

        totals = [
            MonthlyTrendTotal(year=year, month=month, total_amount=total)
            for (year, month), total in sorted(totals_by_month.items())
        ]

        return MonthlyTrendResponse(base_currency=base, items=items, totals_by_month=totals)

    def _resolve_base_currency(self, wallets: list[Wallet], base_currency: str | None) -> str:
        if base_currency:
            return base_currency.upper()
        main = next((w for w in wallets if w.is_main), None)
        return main.currency if main else "RON"

    def _rate_to(self, currency: str, base: str) -> Decimal:
        if currency == base:
            return Decimal("1")
        try:
            return self.fx_service.get_rate(currency, base)
        except ValidationError:
            # FXService's mock rate table doesn't cover every currency a wallet
            # could technically be created in (nothing validates that at
            # wallet-creation time). One unconvertible wallet used to 422 net
            # worth entirely — every wallet, every caller — instead of just
            # that one being shown unconverted.
            return Decimal("1")

    def net_worth(self, user_id: uuid.UUID, base_currency: str | None) -> NetWorthResponse:
        wallets = [w for w in self.wallet_repository.list_for_user(user_id) if w.status != WalletStatus.CLOSED]
        base = self._resolve_base_currency(wallets, base_currency)

        items = []
        total = Decimal("0")
        for wallet in wallets:
            rate = self._rate_to(wallet.currency, base)
            converted = (wallet.available_balance * rate).quantize(_CENTS, rounding=ROUND_HALF_UP)
            total += converted
            items.append(
                WalletBalanceItem(
                    wallet_id=wallet.id,
                    currency=wallet.currency,
                    available_balance=wallet.available_balance,
                    reserved_balance=wallet.reserved_balance,
                    is_main=wallet.is_main,
                    converted_available_balance=converted,
                )
            )
        return NetWorthResponse(base_currency=base, total_available_balance=total, wallets=items)

    def net_worth_history(
        self, user_id: uuid.UUID, period: str, base_currency: str | None
    ) -> NetWorthHistoryResponse:
        now = datetime.now(timezone.utc)
        if period == "1m":
            period_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        elif period in _HISTORY_PERIOD_DAYS:
            period_start = now - timedelta(days=_HISTORY_PERIOD_DAYS[period])
        else:
            raise ValidationError("period must be one of: 1m, 3m, 6m, 1y")

        wallets = [w for w in self.wallet_repository.list_for_user(user_id) if w.status != WalletStatus.CLOSED]
        base = self._resolve_base_currency(wallets, base_currency)

        per_wallet_daily = [
            (wallet.currency, self._wallet_daily_balances(wallet, period_start, period_end=now)) for wallet in wallets
        ]
        all_dates = sorted({day for _, daily in per_wallet_daily for day in daily})

        history = []
        for day in all_dates:
            total = Decimal("0")
            for currency, daily in per_wallet_daily:
                balance = daily.get(day)
                if balance is None:
                    continue
                total += (balance * self._rate_to(currency, base)).quantize(_CENTS, rounding=ROUND_HALF_UP)
            history.append(NetWorthHistoryPoint(date=day, value=total))

        return NetWorthHistoryResponse(base_currency=base, history=history, note=_NET_WORTH_HISTORY_NOTE)

    def _wallet_daily_balances(self, wallet: Wallet, period_start: datetime, period_end: datetime) -> dict:
        """End-of-day available balance for `wallet` on each day from
        max(period_start, wallet.created_at) to min(period_end, now), reconstructed
        from ledger entries rather than a stored history table.

        The opening-balance anchor always uses the real current moment (not
        period_end): wallet.available_balance is always "as of right now", so
        solving for the balance at period_start has to net out ledger changes
        up to now, regardless of how far in the past period_end asks to stop
        displaying. This is what lets the same reconstruction serve both the
        net-worth-history usage (period_end == now) and a bounded historical
        range that ends before today.
        """
        now = datetime.now(timezone.utc)
        wallet_start = max(period_start, wallet.created_at)
        display_end = min(period_end, now)
        opening_balance = wallet.available_balance - self.repository.net_ledger_change(wallet.id, wallet_start, now)
        entries = self.repository.ledger_entries_since(wallet.id, wallet_start)

        balance_by_day: dict = {}
        for _entry_type, _amount, balance_after, created_at in entries:
            if _as_aware_utc(created_at) <= display_end:
                balance_by_day[created_at.date()] = balance_after

        daily: dict = {}
        running = opening_balance
        day = wallet_start.date()
        end_day = display_end.date()
        while day <= end_day:
            if day in balance_by_day:
                running = balance_by_day[day]
            daily[day] = running
            day += timedelta(days=1)
        return daily

    def _resolve_wallet(self, user_id: uuid.UUID, wallet_id: uuid.UUID | None) -> Wallet:
        wallets = self.wallet_repository.list_for_user(user_id)
        if not wallets:
            raise NotFoundError("User has no wallets")

        if wallet_id is not None:
            wallet = next((w for w in wallets if w.id == wallet_id), None)
            if wallet is None:
                raise NotFoundError("Wallet not found")
            return wallet
        return next((w for w in wallets if w.is_main), wallets[0])

    def forecast_month_end_balance(self, user_id: uuid.UUID, wallet_id: uuid.UUID | None) -> ForecastResponse:
        wallet = self._resolve_wallet(user_id, wallet_id)
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        days_elapsed = (now.date() - month_start.date()).days + 1
        days_remaining = days_in_month - days_elapsed

        net_change = self.repository.net_ledger_change(wallet.id, month_start, now)
        average_daily = (net_change / days_elapsed) if days_elapsed > 0 else Decimal("0")
        average_daily = average_daily.quantize(_CENTS, rounding=ROUND_HALF_UP)
        projected_change = (average_daily * days_remaining).quantize(_CENTS, rounding=ROUND_HALF_UP)
        projected_balance = wallet.available_balance + projected_change

        projected_series = [
            ForecastPoint(
                date=(now.date() + timedelta(days=day_offset)),
                projected_balance=(wallet.available_balance + average_daily * day_offset).quantize(
                    _CENTS, rounding=ROUND_HALF_UP
                ),
            )
            for day_offset in range(days_remaining + 1)
        ]

        return ForecastResponse(
            wallet_id=wallet.id,
            currency=wallet.currency,
            current_balance=wallet.available_balance,
            days_elapsed=days_elapsed,
            days_remaining=days_remaining,
            average_daily_net_change=average_daily,
            projected_month_end_balance=projected_balance,
            projected_series=projected_series,
            note=_FORECAST_NOTE,
        )

    def wallet_balance_history(
        self, user_id: uuid.UUID, wallet_id: uuid.UUID | None, date_from: date, date_to: date
    ) -> BalanceHistoryResponse:
        if date_from > date_to:
            raise ValidationError("date_from must not be after date_to")

        wallet = self._resolve_wallet(user_id, wallet_id)

        range_start = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        range_end = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        daily = self._wallet_daily_balances(wallet, range_start, range_end)
        history = [BalanceHistoryPoint(date=day, balance=balance) for day, balance in sorted(daily.items())]

        return BalanceHistoryResponse(
            wallet_id=wallet.id,
            currency=wallet.currency,
            date_from=date_from,
            date_to=date_to,
            history=history,
            note=_BALANCE_HISTORY_NOTE,
        )
