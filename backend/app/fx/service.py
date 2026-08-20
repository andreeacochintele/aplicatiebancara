"""Deterministic FX pricing (architecture.md §5, §44 rule 3: exchange rates
are computed in code, never by an LLM).

`get_quote()` prices actual conversions off the mocked `_RATES_TO_RON` table
so quote math in tests stays exact and offline. `get_market_rate()` is a
separate, read-only path used only for *displaying* a real-world reference
rate (e.g. on the Wallets page): it fetches live ECB rates with a small
markup, falling back to the same static table on any network failure.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.fx.models import FXQuote, FXQuoteStatus
from app.fx.repository import FXQuoteRepository
from app.fx.schemas import FXQuoteRequest

# Mock rates: units of RON per 1 unit of the currency. Used for all quote
# math (transfers, tests) — deterministic and offline on purpose.
_RATES_TO_RON: dict[str, Decimal] = {
    "RON": Decimal("1"),
    "EUR": Decimal("4.97"),
    "USD": Decimal("4.58"),
    "GBP": Decimal("5.80"),
}

FEE_RATE = Decimal("0.005")  # 0.5% of the source amount
QUOTE_VALIDITY_MINUTES = 5
_CENTS = Decimal("0.01")

# Live-rate display path only (see get_market_rate). Frankfurter is ECB-based,
# free and keyless.
_LIVE_RATES_URL = "https://api.frankfurter.app/latest?from=EUR"
_LIVE_RATE_TTL = timedelta(hours=1)
_MARKET_MARKUP = Decimal("0.01")  # 1% bank margin over the raw market rate
_RATE_PRECISION = Decimal("0.0001")
_live_rate_cache: dict[str, Decimal] | None = None
_live_rate_cached_at: datetime | None = None


def _fetch_live_rates_to_ron() -> dict[str, Decimal] | None:
    try:
        with urlopen(_LIVE_RATES_URL, timeout=5) as response:
            payload = json.loads(response.read())
        rates = payload["rates"]
        eur_to_ron = Decimal(str(rates["RON"]))
        live: dict[str, Decimal] = {"RON": Decimal("1"), "EUR": eur_to_ron}
        for currency in ("USD", "GBP"):
            if currency in rates and Decimal(str(rates[currency])) != 0:
                live[currency] = (eur_to_ron / Decimal(str(rates[currency]))).quantize(_RATE_PRECISION)
        return live
    except (URLError, TimeoutError, KeyError, ValueError, TypeError):
        return None


def _rates_to_ron_for_display() -> dict[str, Decimal]:
    global _live_rate_cache, _live_rate_cached_at
    now = datetime.now(timezone.utc)
    if _live_rate_cache is not None and _live_rate_cached_at is not None and now - _live_rate_cached_at < _LIVE_RATE_TTL:
        return _live_rate_cache
    live = _fetch_live_rates_to_ron()
    rates = live if live is not None else dict(_RATES_TO_RON)
    _live_rate_cache, _live_rate_cached_at = rates, now
    return rates


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) drops tzinfo on round-trip even for
    DateTime(timezone=True) columns; Postgres preserves it. Normalize so
    comparisons against `datetime.now(timezone.utc)` work on both."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class FXService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = FXQuoteRepository(db)

    def get_rate(self, source_currency: str, target_currency: str) -> Decimal:
        source_currency, target_currency = source_currency.upper(), target_currency.upper()
        if source_currency not in _RATES_TO_RON or target_currency not in _RATES_TO_RON:
            raise ValidationError(f"Unsupported currency pair: {source_currency}/{target_currency}")
        return _RATES_TO_RON[source_currency] / _RATES_TO_RON[target_currency]

    def get_market_rate(self, source_currency: str, target_currency: str) -> Decimal:
        """Live reference rate for display only (e.g. Wallets), with a small
        margin baked in — never used to price an actual quote/transfer."""
        source_currency, target_currency = source_currency.upper(), target_currency.upper()
        rates = _rates_to_ron_for_display()
        if source_currency not in rates or target_currency not in rates:
            raise ValidationError(f"Unsupported currency pair: {source_currency}/{target_currency}")
        mid_rate = rates[source_currency] / rates[target_currency]
        if source_currency == target_currency:
            return mid_rate
        return (mid_rate * (Decimal("1") - _MARKET_MARKUP)).quantize(_RATE_PRECISION)

    def get_quote(self, user_id: uuid.UUID, data: FXQuoteRequest) -> FXQuote:
        if data.source_amount <= 0:
            raise ValidationError("Amount must be positive")

        source_currency = data.source_currency.upper()
        target_currency = data.target_currency.upper()
        if source_currency == target_currency:
            raise ValidationError("Source and target currency must differ")

        rate = self.get_rate(source_currency, target_currency)
        fee = _round_money(data.source_amount * FEE_RATE)
        target_amount = _round_money((data.source_amount - fee) * rate)

        quote = FXQuote(
            user_id=user_id,
            source_currency=source_currency,
            target_currency=target_currency,
            source_amount=data.source_amount,
            target_amount=target_amount,
            exchange_rate=rate,
            fee=fee,
            status=FXQuoteStatus.CREATED,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=QUOTE_VALIDITY_MINUTES),
        )
        return self.repository.add(quote)

    def get_valid_quote_for_user(self, user_id: uuid.UUID, quote_id: uuid.UUID) -> FXQuote:
        """Fetch a quote and validate it's usable, without consuming it.

        Used by TransactionService when executing a cross-currency transfer —
        the transfer service marks it ACCEPTED only once the transfer itself
        succeeds, so a failed transfer doesn't burn the quote.
        """
        quote = self.repository.get_by_id(quote_id)
        if quote is None or quote.user_id != user_id:
            raise NotFoundError("FX quote not found")
        if quote.status != FXQuoteStatus.CREATED:
            raise ConflictError(f"FX quote is {quote.status.value}, not usable")
        if _as_aware_utc(quote.expires_at) < datetime.now(timezone.utc):
            quote.status = FXQuoteStatus.EXPIRED
            raise ConflictError("FX quote has expired")
        return quote

    def mark_accepted(self, quote: FXQuote) -> None:
        quote.status = FXQuoteStatus.ACCEPTED
