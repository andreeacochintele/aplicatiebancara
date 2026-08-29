"""Typed tools for the Personal Finance Agent (dev4-context.md §8 contract).

Every tool below only calls an existing backend SERVICE and returns its
result unmodified — never touches the DB/SQLAlchemy directly, never
recalculates or reimplements a service's logic:

    Agent -> Tool -> Backend Service -> Database

Two tools from the original contract have no backing data yet and raise
`ToolDataUnavailableError` instead of inventing a figure — see their
docstrings below for exactly what's missing.
"""
import re
from datetime import datetime, timezone

from app.ai.observability import log_tool_call
from app.ai.tools.base import ToolContext, ToolDataUnavailableError
from app.analytics.schemas import CategorySpendingFlag, ForecastResponse, NetWorthResponse, SpendingByTypeResponse
from app.analytics.service import AnalyticsService
from app.budgets.schemas import BudgetPublic
from app.budgets.service import BudgetService
from app.merchants.schemas import MerchantPublic
from app.merchants.service import MerchantService
from app.savings.schemas import SavingsGoalPublic
from app.savings.service import SavingsService
from app.statements.schemas import StatementPublic, StatementRequest
from app.statements.service import StatementService
from app.transactions.schemas import TransactionPublic
from app.transactions.service import TransactionService
from app.wallets.models import WalletStatus
from app.wallets.schemas import WalletPublic
from app.wallets.service import WalletService


@log_tool_call
def get_transactions(ctx: ToolContext) -> list[TransactionPublic]:
    transactions = TransactionService(ctx.db).list_for_user(ctx.user_id)
    return [TransactionPublic.model_validate(t) for t in transactions]


@log_tool_call
def get_spending_by_category(ctx: ToolContext) -> SpendingByTypeResponse:
    """Closest real substitute for "by category": `transaction_categories`
    (Payments/Dev2 module) doesn't exist yet, so this groups the current
    month's spend by TransactionType instead of a real category — same
    limitation analytics/service.py already documents, and the same data
    budgets/service.py's spend tracking is blocked on (dev4-context.md
    §10). Present this to the user as "by type", not "by category"."""
    now = datetime.now(timezone.utc)
    return AnalyticsService(ctx.db).spending_by_type(ctx.user_id, now.year, now.month)


@log_tool_call
def get_spending_recommendations(ctx: ToolContext) -> list[CategorySpendingFlag]:
    """Real per-category spend, unlike get_spending_by_category above —
    reuses AnalyticsService.spending_recommendations(), which groups by
    the paying merchant's own category and only returns categories that
    actually crossed a week-over-week, month-vs-3m-average, or
    concentration threshold. Used by insights.py to phrase the Analytics
    dashboard's "Spending recommendations" panel; the LLM only phrases
    what this tool already decided to flag, never which categories to
    flag (CLAUDE.md §12)."""
    return AnalyticsService(ctx.db).spending_recommendations(ctx.user_id)


@log_tool_call
def get_monthly_income(ctx: ToolContext) -> None:
    """GAP — not implemented on purpose, see agent.py README/report.

    No TransactionType represents incoming/income funds (transactions/
    models.py's TransactionType is TRANSFER/CARD_PAYMENT/FX/CASHBACK/
    LOAN_PAYMENT/SCHEDULED_PAYMENT/BILL_SPLIT_PAYMENT — nothing income-
    shaped), and no service isolates credit-only wallet-ledger movement for
    a period (analytics/repository.py's net_ledger_change() only returns
    the net of credits minus debits, not credits alone). Computing "monthly
    income" here would mean inventing a new aggregate outside the service
    layer, which is exactly what this tool must not do.
    """
    raise ToolDataUnavailableError(
        "Monthly income isn't available yet: there's no transaction type or "
        "service aggregate for incoming funds in the backend."
    )


@log_tool_call
def get_recurring_payments(ctx: ToolContext) -> None:
    """GAP — not implemented on purpose, see agent.py README/report.

    No recurring/subscription detection or storage exists anywhere in the
    codebase (checked transactions/, payments/, scheduled_payments-related
    modules) — this would require new deterministic detection logic in a
    backend service, not something to invent in the AI layer.
    """
    raise ToolDataUnavailableError(
        "Recurring payments aren't available yet: no recurring/subscription "
        "detection exists in the backend."
    )


@log_tool_call
def get_wallet_balances(ctx: ToolContext) -> list[WalletPublic]:
    """Excludes CLOSED wallets: a closed currency's balance is swept to 0 on
    close but the row (and currency) stays, so without this filter a
    currency the user no longer holds would still list as "0.0 available".
    Same filter analytics/service.py already applies in three places."""
    wallets = WalletService(ctx.db).list_wallets(ctx.user_id)
    return [WalletPublic.model_validate(w) for w in wallets if w.status != WalletStatus.CLOSED]


@log_tool_call
def get_net_worth(ctx: ToolContext, target_currency: str | None = None) -> NetWorthResponse:
    """Real FX-converted total across every currency the user holds — reuses
    AnalyticsService.net_worth() as-is (same deterministic FXService.get_rate()
    conversion the Wallets page's net-worth widget already uses), not
    reimplemented here. Sums available_balance only, so reserved amounts are
    excluded from the total by construction, and CLOSED wallets are already
    filtered out by the service. target_currency=None defaults to the user's
    main wallet currency, same default net_worth() itself uses."""
    return AnalyticsService(ctx.db).net_worth(ctx.user_id, target_currency)


@log_tool_call
def get_budgets(ctx: ToolContext) -> list[BudgetPublic]:
    return BudgetService(ctx.db).list_budgets(ctx.user_id)


@log_tool_call
def get_savings_goals(ctx: ToolContext) -> list[SavingsGoalPublic]:
    return SavingsService(ctx.db).list_goals(ctx.user_id)


@log_tool_call
def get_cashback_offers(ctx: ToolContext) -> list[MerchantPublic]:
    """MerchantService has no dedicated "list all offers" method — offers
    are embedded per-merchant (`MerchantPublic.active_offer`) by
    list_merchants(), so this reuses that and filters down to merchants
    that currently have one, rather than adding a new service method."""
    merchants = MerchantService(ctx.db).list_merchants()
    return [merchant for merchant in merchants if merchant.active_offer is not None]


def _select_statement_wallet(wallets: list, message: str | None):
    """Picks which wallet a statement request means: if the message names a
    currency the user actually holds (e.g. "extrasul cont RON"), use that
    wallet even if it isn't main — a user asking for "the RON statement"
    means RON, not whichever wallet happens to be marked main. Falls back
    to the main wallet otherwise, same default every other tool here uses.
    Word-boundary match on the raw message (case-insensitive) — no NLU,
    same keyword-only spirit as the rest of this dispatch layer."""
    active = [w for w in wallets if w.status != WalletStatus.CLOSED]
    if message:
        mentioned = set(re.findall(r"[A-Za-z]{3,}", message.upper()))
        by_currency = next((w for w in active if w.currency.upper() in mentioned), None)
        if by_currency is not None:
            return by_currency
    return next((w for w in active if w.is_main), None)


@log_tool_call
def get_account_statement(ctx: ToolContext, message: str | None = None) -> StatementPublic:
    """Reuses StatementService.generate() as-is — same opening/closing
    balance and totals shown on the Statements page, not recomputed here.
    Period isn't parsed out of the user's message (this dispatch layer is
    keyword-only, see agent.py's module docstring), so this always defaults
    to the current calendar month to date, same default period
    get_spending_by_category already uses. Which wallet IS parsed — see
    _select_statement_wallet — since "show me the RON statement" asking for
    the wrong currency's data outright is a worse failure than not knowing
    the exact date range."""
    wallets = WalletService(ctx.db).list_wallets(ctx.user_id)
    wallet = _select_statement_wallet(wallets, message)
    if wallet is None:
        raise ToolDataUnavailableError("No main wallet to generate a statement for.")

    today = datetime.now(timezone.utc).date()
    return StatementService(ctx.db).generate(
        ctx.user_id,
        StatementRequest(wallet_id=wallet.id, date_from=today.replace(day=1), date_to=today),
    )


@log_tool_call
def forecast_month_end_balance(ctx: ToolContext) -> ForecastResponse:
    """Reuses analytics/service.py's forecast as-is (wallet_ledger_entries
    based, ignores HOLD/RELEASE, already carries its own "simplified"
    disclaimer in `.note`) — not rebuilt here."""
    return AnalyticsService(ctx.db).forecast_month_end_balance(ctx.user_id, wallet_id=None)
