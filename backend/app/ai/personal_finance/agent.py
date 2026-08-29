"""Personal Finance Agent.

Picks one tool from tools.py based on simple keyword matching on the
user's message, calls it, formats its result into an exact deterministic
summary (no LLM involved in producing the numbers), then asks the shared
Azure GPT-5-mini client for a short natural-language framing of that
summary. The framing is prose only — the figures the user sees come
verbatim from the formatted summary the LLM is shown, and that summary is
appended to the reply as-is, so a figure can never be silently
recalculated or rounded by the model (CLAUDE.md §12).

Multi-tool aggregation (e.g. "what did I spend and can I afford a 1500 RON
instalment" spanning Personal Finance + Credit, per architecture.md §29's
orchestrator example) is not implemented — this picks exactly one tool per
message. That's a scope decision for this pass, not an oversight.

`history` (from ai/orchestrator/service.py's short-term conversation
memory) is passed through to the LLM explanation call as prior context —
it never affects which tool gets picked; tool selection is keyword-only
on the current message, same as before history existed.
"""
import uuid

from sqlalchemy.orm import Session

from app.ai.actions.schemas import AgentResult, DownloadAttachment
from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.observability import log_debug, timed_event
from app.ai.personal_finance import tools
from app.ai.tools.base import ToolContext, ToolDataUnavailableError
from app.statements.schemas import StatementPublic

_SYSTEM_PROMPT = (
    "You are the Personal Finance Agent of a banking assistant. You will be "
    "shown the user's real financial data below. That exact data is shown "
    "again to the user, formatted cleanly, immediately after your reply — "
    "so your reply itself must NEVER contain any number, amount, currency "
    "code, percentage, or date, and must NEVER quote, copy, or closely "
    "paraphrase any line, label, or heading from the data — not even the "
    "word 'Data' or a field name. Treat the data purely as something to "
    "react to, not something to reproduce. Write only a short (1-2 "
    "sentence), warm, natural-language reaction to what the data shows — "
    "e.g. a brief acknowledgement or a qualitative observation — never a "
    "restatement, list, or breakdown of it.\n"
    "Be direct and proactive: if the data below clearly answers the user's "
    "question, treat it as answered — do not ask for confirmation first or "
    "offer an optional follow-up ('would you like me to also show...?') "
    "about something the data already covers. Only ask a clarifying "
    "question if the request is genuinely ambiguous about which figure, "
    "category, or time period is needed, or if the data below doesn't "
    "actually cover what they asked. Don't invent a need for clarification "
    "on a request that's already clear just to be cautious.\n"
    "Never claim you calculated, converted, totaled, or otherwise computed "
    "something unless that exact computed result is present in the data "
    "below — e.g. never say 'I calculated the total' or 'I converted this "
    "to RON' if the data below is only a raw, unconverted, per-item listing. "
    "If the data doesn't contain the specific computed figure the user "
    "asked for, say plainly that you don't have that computed figure "
    "(what you do have is below) rather than asserting you performed a "
    "calculation you didn't.\n"
    "Always respond in the same language the user's message is written in. "
    "If the message is ambiguous or too short to tell, default to Romanian."
)

# First keyword match wins; order encodes priority for overlapping words
# (e.g. a "budget" question naming a "category" still routes to budgets).
_DISPATCH: list[tuple[str, tuple[str, ...]]] = [
    ("statement", ("statement", "extras de cont", "extras cont", "extras")),
    ("budgets", ("budget", "buget")),
    ("savings_goals", ("saving", "goal", "econom", "obiectiv")),
    ("cashback_offers", ("cashback", "offer", "discount", "reducere")),
    ("forecast", ("forecast", "end of month", "end-of-month", "project", "prognoz", "proiec")),
    ("income", ("income", "salary", "earn", "venit", "salariu")),
    ("recurring", ("recurring", "subscription", "recurent", "abonament")),
    ("spending_by_type", ("spend", "spent", "spending", "expense", "category", "cheltui", "categorie")),
    ("transactions", ("transaction", "history", "tranzac", "istoric")),
    (
        "net_worth",
        (
            "net worth",
            "total balance",
            "combined balance",
            "all my wallets",
            "all my accounts",
            "toate conturile",
            "toate valutele",
            "sold total",
            "everything combined",
        ),
    ),
    ("wallet_balances", ("balance", "wallet", "money", "how much", "sold", "cont", "bani", "cat am", "cât am")),
]
_DEFAULT_TOOL = "wallet_balances"


def handle(message: str, user_id: uuid.UUID, db: Session, history: list[dict[str, str]] | None = None) -> "str | AgentResult":
    ctx = ToolContext(user_id=user_id, db=db)
    tool_name = _select_tool(message)

    # Special-cased ahead of the generic _SUMMARIZERS dispatch: a statement
    # is the one personal_finance reply the user can also want as a real
    # file, not just chat text, so this needs the underlying StatementPublic
    # (for its wallet_id/date range) in addition to a summary string.
    if tool_name == "statement":
        try:
            statement = tools.get_account_statement(ctx, message)
        except ToolDataUnavailableError as exc:
            return str(exc)
        summary = _format_statement_summary(statement)
        explanation = _explain(message, summary, history)
        reply = _append_summary(explanation, summary)
        download = DownloadAttachment(
            url=(
                f"/statements/export?wallet_id={statement.wallet_id}"
                f"&date_from={statement.date_from}&date_to={statement.date_to}&format=pdf"
            )
        )
        return AgentResult(reply=reply, download=download)

    try:
        summary = _SUMMARIZERS[tool_name](ctx)
    except ToolDataUnavailableError as exc:
        return str(exc)

    explanation = _explain(message, summary, history)
    return _append_summary(explanation, summary)


def _append_summary(explanation: str, summary: str) -> str:
    """Deterministic backstop for the "never quote the data" system-prompt
    rule: a reasoning model doesn't always follow a "never do X" instruction
    (confirmed live — GPT-5-mini occasionally echoes the labeled data block
    verbatim into its own reply despite being told not to). If it already
    did, appending the block again would duplicate it a second time, so
    skip the append in that case instead of trusting the prompt alone."""
    if summary.strip() and summary.strip() in explanation:
        return explanation
    return f"{explanation}\n\n{summary}"


def _select_tool(message: str) -> str:
    lowered = message.lower()
    for tool_name, keywords in _DISPATCH:
        if any(keyword in lowered for keyword in keywords):
            return tool_name
    return _DEFAULT_TOOL


def _explain(message: str, data_summary: str, history: list[dict[str, str]] | None = None) -> str:
    client = get_azure_foundry_client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *(history or []),
        {
            "role": "user",
            "content": (
                f"User asked: {message}\n\n"
                f"(For your reasoning only — never quote, copy, or restate this "
                f"verbatim in your reply, the user will see it separately right "
                f"after your reply:\n{data_summary}\n)"
            ),
        },
    ]
    log_debug("llm_call.request", agent="personal_finance", messages=messages)
    # No temperature override: this GPT-5-mini deployment is a reasoning
    # model that only accepts the default (1) — confirmed live, see
    # azure_foundry_client.py's module docstring.
    with timed_event("llm_call", agent="personal_finance"):
        response = client.chat_completion(messages=messages)
    content = response.choices[0].message.content.strip()
    log_debug("llm_call.response", agent="personal_finance", content=content)
    return content


def _wallet_balances(ctx: ToolContext) -> str:
    wallets = tools.get_wallet_balances(ctx)
    if not wallets:
        return "You don't have any wallets yet."
    lines = [
        f"- {w.currency} {w.available_balance} available"
        + (f" (reserved: {w.reserved_balance})" if w.reserved_balance else "")
        + (" — main wallet" if w.is_main else "")
        for w in wallets
    ]
    return "Wallet balances:\n" + "\n".join(lines)


def _net_worth(ctx: ToolContext) -> str:
    result = tools.get_net_worth(ctx)
    if not result.wallets:
        return "You don't have any wallets yet."
    lines = [
        f"- {w.currency} {w.available_balance} available -> {w.converted_available_balance} {result.base_currency}"
        + (f" (reserved: {w.reserved_balance} {w.currency}, not included in the total)" if w.reserved_balance else "")
        + (" — main wallet" if w.is_main else "")
        for w in result.wallets
    ]
    return (
        f"Total balance across all wallets, converted to {result.base_currency}, "
        f"reserved amounts excluded: {result.total_available_balance} {result.base_currency}\n"
        + "\n".join(lines)
    )


def _transactions(ctx: ToolContext) -> str:
    transactions = tools.get_transactions(ctx)
    if not transactions:
        return "No transactions found yet."
    shown = transactions[:10]
    lines = [
        f"- {t.created_at.date()} {t.type.value}: {t.amount} {t.currency} ({t.status.value})"
        for t in shown
    ]
    header = f"{len(shown)} most recent of {len(transactions)} transactions:\n"
    return header + "\n".join(lines)


def _spending_by_type(ctx: ToolContext) -> str:
    result = tools.get_spending_by_category(ctx)
    header = (
        f"Spending by type, {result.period_start} to {result.period_end} "
        "(grouped by transaction type, not a real category — "
        "transaction_categories doesn't exist yet):\n"
    )
    if not result.items:
        return header + "- no spending recorded"
    lines = [
        f"- {item.type.value}: {item.total_amount} {item.currency} ({item.transaction_count} transactions)"
        for item in result.items
    ]
    return header + "\n".join(lines)


def _budgets(ctx: ToolContext) -> str:
    budgets = tools.get_budgets(ctx)
    if not budgets:
        return "You don't have any budgets set up yet."
    lines = [
        f"- {b.name}: {b.spent_amount}/{b.limit_amount} {b.currency} spent ({b.percent_used}%), "
        f"{b.remaining_amount} {b.currency} remaining, {b.days_remaining} days left in period"
        for b in budgets
    ]
    return "Budgets:\n" + "\n".join(lines)


def _savings_goals(ctx: ToolContext) -> str:
    goals = tools.get_savings_goals(ctx)
    if not goals:
        return "You don't have any savings goals set up yet."
    lines = []
    for g in goals:
        line = f"- {g.name}: {g.current_amount}/{g.target_amount} {g.currency} ({g.percent_complete}%)"
        if g.target_date is not None:
            line += f", target date {g.target_date}"
        if g.monthly_amount_needed is not None:
            line += f", needs {g.monthly_amount_needed} {g.currency}/month to reach it"
        lines.append(line)
    return "Savings goals:\n" + "\n".join(lines)


def _cashback_offers(ctx: ToolContext) -> str:
    merchants = tools.get_cashback_offers(ctx)
    if not merchants:
        return "There are no active cashback offers right now."
    lines = []
    for m in merchants:
        offer = m.active_offer
        line = f"- {m.name} ({m.category}): {offer.cashback_percent}% cashback"
        if offer.maximum_cashback is not None:
            line += f", up to {offer.maximum_cashback}"
        if offer.minimum_spend is not None:
            line += f", minimum spend {offer.minimum_spend}"
        line += f", valid until {offer.end_date}"
        lines.append(line)
    return "Active cashback offers:\n" + "\n".join(lines)


def _format_statement_summary(s: StatementPublic) -> str:
    header = (
        f"Account statement, {s.date_from} to {s.date_to} ({s.currency}):\n"
        f"- Opening balance: {s.opening_balance} {s.currency}\n"
        f"- Closing balance: {s.closing_balance} {s.currency}\n"
        f"- Total incoming: {s.total_incoming} {s.currency}\n"
        f"- Total outgoing: {s.total_outgoing} {s.currency}\n"
    )
    if not s.transactions:
        return header + "No transactions in this period."
    shown = s.transactions[:10]
    lines = [
        f"- {t.created_at.date()} {t.type.value} ({t.direction}): {t.amount} {s.currency} ({t.status.value})"
        + (f" — {t.description}" if t.description else "")
        for t in shown
    ]
    return header + f"{len(shown)} most recent of {len(s.transactions)} transactions:\n" + "\n".join(lines)


def _forecast(ctx: ToolContext) -> str:
    f = tools.forecast_month_end_balance(ctx)
    return (
        f"Month-end forecast: current balance {f.current_balance} {f.currency}, "
        f"projected month-end balance {f.projected_month_end_balance} {f.currency} "
        f"(average daily net change {f.average_daily_net_change} {f.currency}, "
        f"{f.days_remaining} days remaining). Note: {f.note}"
    )


def _income(ctx: ToolContext) -> str:
    tools.get_monthly_income(ctx)
    return ""  # unreachable: get_monthly_income always raises ToolDataUnavailableError


def _recurring(ctx: ToolContext) -> str:
    tools.get_recurring_payments(ctx)
    return ""  # unreachable: get_recurring_payments always raises ToolDataUnavailableError


_SUMMARIZERS = {
    "net_worth": _net_worth,
    "wallet_balances": _wallet_balances,
    "transactions": _transactions,
    "spending_by_type": _spending_by_type,
    "budgets": _budgets,
    "savings_goals": _savings_goals,
    "cashback_offers": _cashback_offers,
    "forecast": _forecast,
    "income": _income,
    "recurring": _recurring,
}
