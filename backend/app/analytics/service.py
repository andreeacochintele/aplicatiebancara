"""Analytics business rules: read-only aggregates over the transaction and wallet data
other modules own. Currency conversion is delegated to FXService (fx/service.py) rather
than re-deriving rates here — analytics only aggregates, it never prices FX itself."""
import calendar
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.analytics.repository import AnalyticsRepository
from app.analytics.schemas import (
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
    WalletBalanceItem,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.fx.service import FXService
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

_HISTORY_PERIOD_DAYS = {"3m": 90, "6m": 182, "1y": 365}

_CENTS = Decimal("0.01")


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AnalyticsRepository(db)
        self.wallet_repository = WalletRepository(db)
        self.fx_service = FXService(db)

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
            (wallet.currency, self._wallet_daily_balances(wallet, period_start, now)) for wallet in wallets
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

    def _wallet_daily_balances(self, wallet: Wallet, period_start: datetime, now: datetime) -> dict:
        """End-of-day available balance for `wallet` on each day from
        max(period_start, wallet.created_at) to now, reconstructed from ledger
        entries rather than a stored history table."""
        wallet_start = max(period_start, wallet.created_at)
        opening_balance = wallet.available_balance - self.repository.net_ledger_change(wallet.id, wallet_start, now)
        entries = self.repository.ledger_entries_since(wallet.id, wallet_start)

        balance_by_day: dict = {}
        for _entry_type, _amount, balance_after, created_at in entries:
            balance_by_day[created_at.date()] = balance_after

        daily: dict = {}
        running = opening_balance
        day = wallet_start.date()
        end_day = now.date()
        while day <= end_day:
            if day in balance_by_day:
                running = balance_by_day[day]
            daily[day] = running
            day += timedelta(days=1)
        return daily

    def forecast_month_end_balance(self, user_id: uuid.UUID, wallet_id: uuid.UUID | None) -> ForecastResponse:
        wallets = self.wallet_repository.list_for_user(user_id)
        if not wallets:
            raise NotFoundError("User has no wallets")

        if wallet_id is not None:
            wallet = next((w for w in wallets if w.id == wallet_id), None)
            if wallet is None:
                raise NotFoundError("Wallet not found")
        else:
            wallet = next((w for w in wallets if w.is_main), wallets[0])

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
