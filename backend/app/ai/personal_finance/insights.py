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
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.guardrails import language_directive
from app.ai.observability import log_debug, timed_event
from app.ai.personal_finance import tools
from app.ai.personal_finance.models import AIInsight
from app.ai.personal_finance.repository import AIInsightRepository
from app.ai.tools.base import ToolContext
from app.analytics.schemas import CategorySpendingFlag
from app.core.exceptions import NotFoundError

INSIGHT_TTL = timedelta(hours=24)
# Shorter TTL specifically for a cached ALL_CLEAR row: spending_recommendations()
# used to go silently empty for the first few days of every calendar week/month
# (fixed by switching to rolling windows — see analytics/service.py), and a
# 24h-cached all-clear from that gap could otherwise mask real activity for
# most of a day. An ALL_CLEAR is the cheap case to re-check (an empty flags
# list, not a real Azure call — generate_and_store only calls the LLM per
# flagged category), so re-checking hourly costs nothing when there's still
# nothing to flag.
ALL_CLEAR_TTL = timedelta(hours=1)

_ALL_CLEAR_MESSAGES = {
    "en": [
        "Nothing unusual in your spending lately — you're doing great! 🎉",
        "All quiet on the spending front — nothing to flag right now.",
        "No red flags here — your spending looks steady and on track.",
        "Smooth sailing lately — nothing stood out in your spending.",
        "Nothing to report — your spending's been nice and boring (the good kind) 👍",
    ],
    "ro": [
        "Nimic ieșit din comun la cheltuieli în ultima vreme — te descurci grozav! 🎉",
        "Liniște totală pe front financiar — nimic de semnalat acum.",
        "Niciun semnal de alarmă — cheltuielile tale arată stabile și pe drumul cel bun.",
        "Liniște în ultima vreme — nimic nu a ieșit în evidență la cheltuieli.",
        "Nimic de raportat — cheltuielile tale au fost plăcut de liniștite 👍",
    ],
}


def _build_system_prompt(locale: str) -> str:
    intro = {
        "en": (
            "You are the Personal Finance Agent of a banking assistant, writing a single "
            "short spending-recommendation notification for a category that a deterministic "
            "backend check already flagged.\n\n"
            "Voice: you're a friendly, upbeat financial buddy talking to a friend — not a "
            "compliance officer. Warm, encouraging, a little playful. Casual, conversational "
            "language. Light emoji where it feels natural (not on every message). Celebrate "
            "when things go well; when flagging overspending, be gently teasing, never "
            "shaming or lecturing.\n\n"
            "Write ONE short message (max 2 sentences). Use ONLY the figures given below; "
            "never invent, recalculate, or round a number yourself. Do not repeat every "
            "figure verbatim — summarize naturally, but ALWAYS state the currency when "
            "citing a percentage-of-total figure (e.g. 'accounts for 53% of your EUR "
            "spending') — this user has spending in more than one currency, and "
            "every figure below is scoped to one currency only, never blended across "
            "currencies. The figures below are rolling windows (the last 7 days, and the "
            "last 30 days), NOT a Monday-to-Sunday week or a calendar month — never say "
            "'this week', 'last week', 'this month', or any calendar-period word; say "
            "'the last 7 days' / 'lately' / 'over the last month' (as a duration, not a "
            "calendar month) instead.\n\n"
            "Examples (tone reference only — never reuse these numbers):\n\n"
            "Stiff (AVOID): \"Your Entertainment category spending has increased by 42% "
            "compared to the previous week, exceeding the recommended threshold.\"\n"
            "Buddy (WRITE LIKE THIS): \"Whoa, Entertainment's had a big stretch 🎬 — up 42% "
            "over the last 7 days. Worth reining it in a little?\"\n\n"
            "Stiff (AVOID): \"This category represents 53% of your total monthly "
            "expenditure in EUR.\"\n"
            "Buddy (WRITE LIKE THIS): \"Heads up — dining out is eating over half your EUR "
            "spending lately (53%!). No judgment, just flagging it 😅\"\n\n"
            "Output only the message itself, no preamble."
        ),
        "ro": (
            "Ești Personal Finance Agent-ul unui asistent bancar, scriind o singură "
            "notificare scurtă de recomandare de cheltuieli pentru o categorie deja "
            "semnalată de o verificare deterministă din backend.\n\n"
            "Voce: ești un prieten priceput la bani care vorbește cu un prieten — nu un "
            "ofițer de conformitate. Cald, încurajator, puțin jucăuș. Limbaj casual, "
            "conversațional, la persoana a II-a singular (\"tu\", niciodată "
            "\"dumneavoastră\"). Emoji ușor, acolo unde se potrivește natural (nu la "
            "fiecare mesaj). Sărbătorește când lucrurile merg bine; când semnalezi "
            "cheltuieli în exces, tachinează ușor, fără să faci pe cineva să se simtă "
            "vinovat și fără ton de morală. Evită construcții rigide gen \"Vă recomandăm "
            "să...\" sau \"Este recomandat să...\".\n\n"
            "Scrie UN singur mesaj scurt (maxim 2 propoziții). Folosește DOAR cifrele date "
            "mai jos; nu inventa, nu recalcula și nu rotunji nicio cifră. Nu repeta fiecare "
            "cifră mot-a-mot — rezumă natural, dar menționează ÎNTOTDEAUNA moneda când "
            "citezi un procent din total (ex. \"reprezintă 53% din cheltuielile tale în "
            "EUR\") — acest utilizator are cheltuieli în mai multe monede, iar "
            "fiecare cifră de mai jos e limitată la o singură monedă, niciodată "
            "combinată. Cifrele de mai jos sunt ferestre mobile (ultimele 7 zile, respectiv "
            "ultimele 30 de zile), NU o săptămână luni-duminică sau o lună calendaristică — "
            "nu spune niciodată \"săptămâna asta\", \"săptămâna trecută\", \"luna asta\" sau "
            "orice cuvânt care sugerează o perioadă calendaristică fixă; spune \"în ultimele "
            "7 zile\" / \"în ultima vreme\" / \"în ultima lună\" (ca durată, nu ca lună "
            "calendaristică) în schimb.\n\n"
            "Exemple (doar pentru ton — nu refolosi aceste cifre):\n\n"
            "Rigid (EVITĂ): \"Cheltuielile dumneavoastră la categoria Divertisment au "
            "crescut cu 42% față de săptămâna precedentă, depășind pragul recomandat.\"\n"
            "Prietenos (SCRIE AȘA): \"Uau, Divertisment a avut o perioadă pe cinste 🎬 — cu "
            "42% mai mult în ultimele 7 zile. Poate o mai lași mai domol?\"\n\n"
            "Rigid (EVITĂ): \"Această categorie reprezintă 53% din cheltuielile "
            "dumneavoastră lunare totale în EUR.\"\n"
            "Prietenos (SCRIE AȘA): \"Ia uite — ieșitul în oraș îți mănâncă peste jumătate "
            "din cheltuielile tale în EUR în ultima vreme (53%!). Fără judecăți, doar să "
            "știi 😅\"\n\n"
            "Răspunde doar cu mesajul propriu-zis, fără introducere."
        ),
    }
    return f"{intro.get(locale, intro['ro'])}\n\n{language_directive(locale)}"


_SYSTEM_PROMPTS = {"ro": _build_system_prompt("ro"), "en": _build_system_prompt("en")}


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _format_flag_summary(flag: CategorySpendingFlag) -> str:
    lines = [f"Category: {flag.category} ({flag.currency})", f"Reasons flagged: {', '.join(flag.reasons)}"]
    week = flag.week_over_week
    if week is not None and week.change_percent is not None:
        lines.append(
            f"Last 7 days: {week.current_amount} {flag.currency} vs the 7 days before that: "
            f"{week.comparison_amount} {flag.currency} ({week.change_percent:.0f}% change)"
        )
    month = flag.month_vs_three_month_average
    if month is not None and month.change_percent is not None:
        lines.append(
            f"Last 30 days: {month.current_amount} {flag.currency} vs this category's "
            f"average over the 90 days before that: {month.comparison_amount} {flag.currency} "
            f"({month.change_percent:.0f}% change)"
        )
    if flag.share_of_total_percent is not None:
        lines.append(
            f"This category is {flag.share_of_total_percent}% of the last 30 days' total {flag.currency} spending "
            f"(spending in other currencies is tracked separately and is not part of this percentage)."
        )
    return "\n".join(lines)


def _phrase_flag(flag: CategorySpendingFlag, locale: str = "ro") -> str:
    client = get_azure_foundry_client()
    system_prompt = _SYSTEM_PROMPTS.get(locale, _SYSTEM_PROMPTS["ro"])
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _format_flag_summary(flag)},
    ]
    log_debug("llm_call.request", agent="personal_finance_insights", messages=messages)
    with timed_event("llm_call", agent="personal_finance_insights"):
        response = client.chat_completion(messages=messages)
    content = response.choices[0].message.content.strip()
    log_debug("llm_call.response", agent="personal_finance_insights", content=content)
    return content


def _period_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def generate_and_store(
    db: Session, user_id: uuid.UUID, locale: str = "ro", as_of: datetime | None = None
) -> list[AIInsight]:
    """Always writes at least one row, even when nothing is flagged — a
    quiet period still needs a fresh created_at so get_or_generate() doesn't
    re-check (and re-call Azure) on every request for a user with no
    notable spending changes. Supersedes (dismisses) whatever the previous
    batch for this same period_key left active first, so a regeneration
    replaces it rather than piling new rows on top of stale ones — a
    different period's already-cached batch is untouched.

    `as_of` (defaults to now) is both the reference point
    spending_recommendations() scores against AND what decides which
    period_key this batch is filed under — see get_or_generate()."""
    target = as_of or datetime.now(timezone.utc)
    period_key = _period_key(target)
    repository = AIInsightRepository(db)
    repository.supersede_active_for_user(user_id, period_key)
    flags = tools.get_spending_recommendations(ToolContext(user_id=user_id, db=db), as_of=target)

    if not flags:
        variants = _ALL_CLEAR_MESSAGES.get(locale, _ALL_CLEAR_MESSAGES["ro"])
        insight = repository.add(
            AIInsight(
                user_id=user_id,
                period_key=period_key,
                message=random.choice(variants),
                category=None,
                currency=None,
                insight_type="ALL_CLEAR",
            )
        )
        db.flush()
        return [insight]

    created = [
        repository.add(
            AIInsight(
                user_id=user_id,
                period_key=period_key,
                message=_phrase_flag(flag, locale),
                category=flag.category,
                currency=flag.currency,
                insight_type=",".join(flag.reasons),
            )
        )
        for flag in flags
    ]
    db.flush()
    return created


def get_or_generate(
    db: Session, user_id: uuid.UUID, force: bool = False, locale: str = "ro", as_of: datetime | None = None
) -> list[AIInsight]:
    """force=True (the Analytics page's refresh button) bypasses the TTL
    and always regenerates, same as a natural TTL expiry would - it does
    not skip the ledger of what changed, it just triggers early. That TTL
    only applies to the real current month though — a past month's figures
    never change once the month is closed, so a cached past-month batch is
    never regenerated automatically just because time passed.

    It IS regenerated if the active list for that period is empty — either
    nothing was ever generated for it, or the user dismissed every insight
    from the last batch. Without the second case, dismissing everything in
    a past month would be a one-way door: no TTL ever brings a closed
    month's advice back, so the panel would stay permanently empty with no
    way to see it again. The flags themselves are deterministic (same
    transactions, same as_of point), so a regeneration here can only ever
    reproduce the same substance with fresh LLM wording — never new,
    surprising advice appearing days later, which is the actual cost the
    permanent-cache design exists to avoid."""
    now = datetime.now(timezone.utc)
    target = as_of or now
    if target > now:
        target = now  # a future period makes no sense; fall back to now
    period_key = _period_key(target)
    is_current_period = period_key == _period_key(now)

    repository = AIInsightRepository(db)
    latest = repository.latest_for_user(user_id, period_key)

    if latest is None:
        generate_and_store(db, user_id, locale, target)
    elif is_current_period:
        ttl = ALL_CLEAR_TTL if latest.insight_type == "ALL_CLEAR" else INSIGHT_TTL
        if force or _as_aware_utc(latest.created_at) < now - ttl:
            generate_and_store(db, user_id, locale, target)
    elif force or not repository.list_active_for_user(user_id, period_key, limit=1):
        generate_and_store(db, user_id, locale, target)

    return repository.list_active_for_user(user_id, period_key)


def dismiss(db: Session, user_id: uuid.UUID, insight_id: uuid.UUID) -> None:
    repository = AIInsightRepository(db)
    insight = repository.get_by_id(insight_id)
    if insight is None or insight.user_id != user_id:
        raise NotFoundError("Insight not found")
    insight.dismissed = True
    db.flush()
