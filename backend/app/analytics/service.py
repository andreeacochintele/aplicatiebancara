"""Analytics business rules: read-only aggregates over the transaction and wallet data
other modules own. Currency conversion is delegated to FXService (fx/service.py) rather
than re-deriving rates here — analytics only aggregates, it never prices FX itself."""
import calendar
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.analytics.repository import AnalyticsRepository
from app.analytics.schemas import (
    ForecastResponse,
    MonthlyTrendItem,
    MonthlyTrendResponse,
    NetWorthResponse,
    SpendingByType,
    SpendingByTypeResponse,
    WalletBalanceItem,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.fx.service import FXService
from app.wallets.repository import WalletRepository

_FORECAST_NOTE = (
    "Simplified projection based on this month's ledger trend only — does not "
    "yet account for scheduled payments or loan instalments."
)

_CENTS = Decimal("0.01")


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AnalyticsRepository(db)
        self.wallet_repository = WalletRepository(db)
        self.fx_service = FXService(db)

    def spending_by_type(self, user_id: uuid.UUID, year: int | None, month: int | None) -> SpendingByTypeResponse:
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

        rows = self.repository.spending_by_type(user_id, period_start, period_end)
        items = [
            SpendingByType(type=tx_type, total_amount=total, currency=currency, transaction_count=count)
            for tx_type, currency, total, count in rows
        ]
        return SpendingByTypeResponse(
            period_start=period_start.date(), period_end=period_end.date(), items=items
        )

    def monthly_trend(self, user_id: uuid.UUID, months: int) -> MonthlyTrendResponse:
        if not 1 <= months <= 24:
            raise ValidationError("months must be between 1 and 24")

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
        return MonthlyTrendResponse(items=items)

    def net_worth(self, user_id: uuid.UUID, base_currency: str | None) -> NetWorthResponse:
        wallets = self.wallet_repository.list_for_user(user_id)
        if base_currency:
            base = base_currency.upper()
        else:
            main = next((w for w in wallets if w.is_main), None)
            base = main.currency if main else "RON"

        items = []
        total = Decimal("0")
        for wallet in wallets:
            rate = Decimal("1") if wallet.currency == base else self.fx_service.get_rate(wallet.currency, base)
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

        return ForecastResponse(
            wallet_id=wallet.id,
            currency=wallet.currency,
            current_balance=wallet.available_balance,
            days_elapsed=days_elapsed,
            days_remaining=days_remaining,
            average_daily_net_change=average_daily,
            projected_month_end_balance=projected_balance,
            note=_FORECAST_NOTE,
        )
