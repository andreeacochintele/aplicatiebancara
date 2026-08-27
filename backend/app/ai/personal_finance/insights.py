"""Generates and caches the Analytics dashboard's "Spending recommendations"
panel — a short list of AIInsight rows per user, refreshed lazily.

Flow: Tool -> LLM phrasing -> AIInsight rows (Agent -> Tool -> Service ->
Database, same contract every other tool in this package follows). The
LLM is never shown raw transactions and never decides which categories
matter — tools.get_spending_recommendations() (a thin wrapper over
AnalyticsService.spending_recommendations(), pure calculation, no AI)
already decided that; the model here only turns each flagged category's
numbers into one short sentence (CLAUDE.md §12).

No background scheduler exists in this project (checked: no APScheduler/
Celery/cron anywhere in the repo — see also payments/service.py's
scheduled-payments module, which has the same gap). Regenerating on
every dashboard load would mean a real Azure call per page view, so
get_or_generate() instead checks the newest AIInsight row's age and only
regenerates once INSIGHT_TTL has passed — same "generate once, cache in
a DB column/table, serve from cache" idea FraudCase.agent_analysis
already uses, just time-based instead of admin-action-triggered.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.observability import log_debug, timed_event
from app.ai.personal_finance import tools
from app.ai.personal_finance.models import AIInsight
from app.ai.personal_finance.repository import AIInsightRepository
from app.ai.tools.base import ToolContext
from app.analytics.schemas import CategorySpendingFlag
from app.core.exceptions import NotFoundError

INSIGHT_TTL = timedelta(hours=24)

_ALL_CLEAR_MESSAGE = "Nothing unusual to flag in your spending this week — keep it up!"

_SYSTEM_PROMPT = (
    "You are the Personal Finance Agent of a banking assistant, writing a single "
    "short spending-recommendation notification for a category that a deterministic "
    "backend check already flagged. Write ONE short message (max 2 sentences), "
    "friendly, direct, and actionable — matching this tone exactly: "
    "'You spent noticeably more on Entertainment this week — consider dialing it "
    "back next week.' Use ONLY the figures given below; never invent, recalculate, "
    "or round a number yourself. Do not repeat every figure verbatim — summarize "
    "naturally, but ALWAYS state the currency when citing a percentage-of-total "
    "figure (e.g. 'accounts for 53% of your EUR spending this month') — this "
    "user has spending in more than one currency, and every figure below is "
    "scoped to one currency only, never blended across currencies. Respond in "
    "English. Output only the message itself, no preamble."
)


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _format_flag_summary(flag: CategorySpendingFlag) -> str:
    lines = [f"Category: {flag.category} ({flag.currency})", f"Reasons flagged: {', '.join(flag.reasons)}"]
    week = flag.week_over_week
    if week is not None and week.change_percent is not None:
        lines.append(
            f"This week so far: {week.current_amount} {flag.currency} vs last week: "
            f"{week.comparison_amount} {flag.currency} ({week.change_percent:.0f}% change)"
        )
    month = flag.month_vs_three_month_average
    if month is not None and month.change_percent is not None:
        lines.append(
            f"This month so far: {month.current_amount} {flag.currency} vs this category's "
            f"average over the prior 3 months: {month.comparison_amount} {flag.currency} "
            f"({month.change_percent:.0f}% change)"
        )
    if flag.share_of_total_percent is not None:
        lines.append(
            f"This category is {flag.share_of_total_percent}% of this month's total {flag.currency} spending "
            f"(spending in other currencies is tracked separately and is not part of this percentage)."
        )
    return "\n".join(lines)


def _phrase_flag(flag: CategorySpendingFlag) -> str:
    client = get_azure_foundry_client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _format_flag_summary(flag)},
    ]
    log_debug("llm_call.request", agent="personal_finance_insights", messages=messages)
    with timed_event("llm_call", agent="personal_finance_insights"):
        response = client.chat_completion(messages=messages)
    content = response.choices[0].message.content.strip()
    log_debug("llm_call.response", agent="personal_finance_insights", content=content)
    return content


def generate_and_store(db: Session, user_id: uuid.UUID) -> list[AIInsight]:
    """Always writes at least one row, even when nothing is flagged — a
    quiet week still needs a fresh created_at so get_or_generate() doesn't
    re-check (and re-call Azure) on every request for a user with no
    notable spending changes. Supersedes (dismisses) whatever the
    previous batch left active first, so a regeneration replaces it
    rather than piling new rows on top of stale ones."""
    repository = AIInsightRepository(db)
    repository.supersede_active_for_user(user_id)
    flags = tools.get_spending_recommendations(ToolContext(user_id=user_id, db=db))

    if not flags:
        insight = repository.add(
            AIInsight(
                user_id=user_id, message=_ALL_CLEAR_MESSAGE, category=None, currency=None, insight_type="ALL_CLEAR"
            )
        )
        db.flush()
        return [insight]

    created = [
        repository.add(
            AIInsight(
                user_id=user_id,
                message=_phrase_flag(flag),
                category=flag.category,
                currency=flag.currency,
                insight_type=",".join(flag.reasons),
            )
        )
        for flag in flags
    ]
    db.flush()
    return created


def get_or_generate(db: Session, user_id: uuid.UUID, force: bool = False) -> list[AIInsight]:
    """force=True (the Analytics page's refresh button) bypasses the TTL
    and always regenerates, same as a natural TTL expiry would - it does
    not skip the ledger of what changed, it just triggers early."""
    repository = AIInsightRepository(db)
    latest = repository.latest_created_at(user_id)
    if force or latest is None or _as_aware_utc(latest) < datetime.now(timezone.utc) - INSIGHT_TTL:
        generate_and_store(db, user_id)
    return repository.list_active_for_user(user_id)


def dismiss(db: Session, user_id: uuid.UUID, insight_id: uuid.UUID) -> None:
    repository = AIInsightRepository(db)
    insight = repository.get_by_id(insight_id)
    if insight is None or insight.user_id != user_id:
        raise NotFoundError("Insight not found")
    insight.dismissed = True
    db.flush()
