import calendar
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ai.personal_finance import insights
from app.ai.personal_finance.models import AIInsight
from app.ai.personal_finance.repository import AIInsightRepository
from app.core.exceptions import NotFoundError
from app.merchants.models import Merchant
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="pf-insights-user@example.com", password="Sup3rSecret!", first_name="PF", last_name="Insights")
    )


def _mock_phrase(monkeypatch):
    calls: list[str] = []

    def _fake(flag, locale="ro"):
        calls.append(flag.category)
        return f"Mocked message about {flag.category}."

    monkeypatch.setattr(insights, "_phrase_flag", _fake)
    return calls


def _current_period_key() -> str:
    return insights._period_key(datetime.now(timezone.utc))


def _add_flagged_category(db_session, user, wallet):
    """A category with a clear week-over-week spike, guaranteed to be
    flagged by AnalyticsService.spending_recommendations(). Uses a fixed
    day-offset (10 days ago, comfortably inside the rolling "prior 7-14
    days" window regardless of what day of the week the suite runs) rather
    than calendar Monday-based arithmetic — the same class of boundary
    flakiness this rolling-window design was built to avoid in the first
    place (see analytics/service.py's spending_recommendations())."""
    now = datetime.now(timezone.utc)
    ten_days_ago = now - timedelta(days=10)
    cinema = Merchant(name="Cinema City", category="Entertainment", verified=True)
    db_session.add(cinema)
    db_session.flush()
    for amount, when in (("50.00", ten_days_ago), ("500.00", now)):
        db_session.add(
            Transaction(
                initiator_user_id=user.id,
                source_wallet_id=wallet.id,
                merchant_id=cinema.id,
                type=TransactionType.CARD_PAYMENT,
                status=TransactionStatus.COMPLETED,
                amount=Decimal(amount),
                currency="RON",
                created_at=when,
            )
        )
    db_session.flush()


@pytest.fixture()
def seeded_wallet(db_session, seeded_user):
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    db_session.flush()
    return wallet


def test_generate_and_store_creates_one_insight_per_flagged_category(db_session, seeded_user, seeded_wallet, monkeypatch):
    calls = _mock_phrase(monkeypatch)
    _add_flagged_category(db_session, seeded_user, seeded_wallet)

    created = insights.generate_and_store(db_session, seeded_user.id)

    assert calls == ["Entertainment"]
    assert len(created) == 1
    assert created[0].category == "Entertainment"
    assert created[0].currency == "RON"
    assert created[0].message == "Mocked message about Entertainment."
    assert "WEEK_OVER_WEEK_INCREASE" in created[0].insight_type
    assert created[0].dismissed is False


def test_generate_and_store_writes_all_clear_when_nothing_flagged(db_session, seeded_user, monkeypatch):
    calls = _mock_phrase(monkeypatch)

    created = insights.generate_and_store(db_session, seeded_user.id)

    assert calls == []
    assert len(created) == 1
    assert created[0].insight_type == "ALL_CLEAR"
    assert created[0].category is None
    assert created[0].currency is None
    assert created[0].message in insights._ALL_CLEAR_MESSAGES["ro"]  # default locale


def test_generate_and_store_writes_all_clear_in_the_requested_locale(db_session, seeded_user):
    created = insights.generate_and_store(db_session, seeded_user.id, locale="en")

    assert created[0].message in insights._ALL_CLEAR_MESSAGES["en"]
    assert created[0].message not in insights._ALL_CLEAR_MESSAGES["ro"]


def test_all_clear_message_pools_have_multiple_distinct_variants_per_locale():
    for locale, variants in insights._ALL_CLEAR_MESSAGES.items():
        assert 3 <= len(variants) <= 5
        assert len(set(variants)) == len(variants)  # no duplicates


def test_phrase_flag_uses_the_requested_locales_system_prompt(db_session, seeded_user, seeded_wallet, monkeypatch):
    _add_flagged_category(db_session, seeded_user, seeded_wallet)
    captured = {}

    class _FakeMessage:
        content = "Mocked reply."

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeClient:
        def chat_completion(self, messages):
            captured["system_prompt"] = messages[0]["content"]
            return _FakeResponse()

    monkeypatch.setattr(insights, "get_azure_foundry_client", lambda: _FakeClient())

    insights.generate_and_store(db_session, seeded_user.id, locale="en")

    assert captured["system_prompt"] == insights._SYSTEM_PROMPTS["en"]
    assert "friendly, upbeat financial buddy" in captured["system_prompt"]


def test_generate_and_store_keeps_same_category_separate_per_currency(db_session, seeded_user, monkeypatch):
    """The bug report this fix addresses: a category split across two
    currencies (e.g. Travel in both RON and EUR) must produce two
    separate, separately-labeled insights - never one figure blended or
    mistaken for the other."""
    from app.merchants.models import Merchant

    calls = _mock_phrase(monkeypatch)
    now = datetime.now(timezone.utc)
    wallet_ron = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    wallet_eur = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="EUR"))
    db_session.flush()
    emirates = Merchant(name="Emirates", category="Travel", verified=True)
    zara = Merchant(name="Zara", category="Retail", verified=True)
    db_session.add_all([emirates, zara])
    db_session.flush()

    # RON: Travel is a small share of a large total -> not concentrated.
    db_session.add(Transaction(initiator_user_id=seeded_user.id, source_wallet_id=wallet_ron.id, merchant_id=emirates.id, type=TransactionType.CARD_PAYMENT, status=TransactionStatus.COMPLETED, amount=Decimal("100.00"), currency="RON", created_at=now))
    db_session.add(Transaction(initiator_user_id=seeded_user.id, source_wallet_id=wallet_ron.id, merchant_id=zara.id, type=TransactionType.CARD_PAYMENT, status=TransactionStatus.COMPLETED, amount=Decimal("900.00"), currency="RON", created_at=now))
    # EUR: Travel is the only EUR spend -> 100% concentrated.
    db_session.add(Transaction(initiator_user_id=seeded_user.id, source_wallet_id=wallet_eur.id, merchant_id=emirates.id, type=TransactionType.CARD_PAYMENT, status=TransactionStatus.COMPLETED, amount=Decimal("400.00"), currency="EUR", created_at=now))
    db_session.flush()

    created = insights.generate_and_store(db_session, seeded_user.id)

    travel_insights = [i for i in created if i.category == "Travel"]
    assert len(travel_insights) == 1
    assert travel_insights[0].currency == "EUR"


def test_get_or_generate_does_not_regenerate_within_ttl(db_session, seeded_user, seeded_wallet, monkeypatch):
    calls = _mock_phrase(monkeypatch)
    _add_flagged_category(db_session, seeded_user, seeded_wallet)

    first = insights.get_or_generate(db_session, seeded_user.id)
    assert len(calls) == 1

    second = insights.get_or_generate(db_session, seeded_user.id)

    assert len(calls) == 1  # not called again
    assert [i.id for i in second] == [i.id for i in first]


def test_get_or_generate_regenerates_after_ttl_expires(db_session, seeded_user, seeded_wallet, monkeypatch):
    calls = _mock_phrase(monkeypatch)
    _add_flagged_category(db_session, seeded_user, seeded_wallet)

    insights.get_or_generate(db_session, seeded_user.id)
    assert len(calls) == 1

    # Backdate the cached row past the TTL.
    stale_cutoff = datetime.now(timezone.utc) - insights.INSIGHT_TTL - timedelta(minutes=1)
    for insight in db_session.query(AIInsight).filter(AIInsight.user_id == seeded_user.id):
        insight.created_at = stale_cutoff
    db_session.flush()

    first_insight_id = AIInsightRepository(db_session).list_active_for_user(seeded_user.id, _current_period_key())[0].id

    active = insights.get_or_generate(db_session, seeded_user.id)

    assert len(calls) == 2
    # The stale batch was superseded (dismissed), not left active alongside
    # the fresh one - regenerating must never pile up duplicates.
    assert len(active) == 1
    assert active[0].id != first_insight_id


def test_get_or_generate_force_bypasses_ttl_and_supersedes_old_batch(db_session, seeded_user, seeded_wallet, monkeypatch):
    calls = _mock_phrase(monkeypatch)
    _add_flagged_category(db_session, seeded_user, seeded_wallet)

    insights.get_or_generate(db_session, seeded_user.id)
    assert len(calls) == 1
    first_insight_id = AIInsightRepository(db_session).list_active_for_user(seeded_user.id, _current_period_key())[0].id

    # Still well within the TTL - a plain get_or_generate would not
    # regenerate, but force=True (the dashboard's refresh button) must.
    active = insights.get_or_generate(db_session, seeded_user.id, force=True)

    assert len(calls) == 2
    assert len(active) == 1
    assert active[0].id != first_insight_id


# ---- per-period caching: a past (closed) month's recommendations never
# change once generated, so they're cached forever, while the real current
# month keeps its live TTL — see get_or_generate()'s docstring.


def _months_ago_end(months_back: int) -> datetime:
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    days_in_month = calendar.monthrange(year, month)[1]
    return datetime(year, month, days_in_month, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_get_or_generate_for_a_past_month_never_regenerates_without_force(db_session, seeded_user):
    # No flagged-category fixture here on purpose: this asserts on row
    # identity (did generation happen at all), not on _phrase_flag call
    # counts, since a past period with no data legitimately comes back
    # ALL_CLEAR (no LLM call either way) — see the "independent" test below
    # for the case where a period does have something to flag.
    past = _months_ago_end(2)

    first = insights.get_or_generate(db_session, seeded_user.id, as_of=past)

    # Backdate the cached row far past the (irrelevant, for a closed month)
    # TTL — must still not regenerate, since a closed month's cache never
    # expires on its own.
    for insight in db_session.query(AIInsight).filter(AIInsight.user_id == seeded_user.id):
        insight.created_at = datetime.now(timezone.utc) - insights.INSIGHT_TTL * 10
    db_session.flush()

    second = insights.get_or_generate(db_session, seeded_user.id, as_of=past)

    assert [i.id for i in second] == [i.id for i in first]  # same rows, no regeneration


def test_get_or_generate_for_a_past_month_honors_explicit_force(db_session, seeded_user):
    past = _months_ago_end(2)

    first = insights.get_or_generate(db_session, seeded_user.id, as_of=past)
    second = insights.get_or_generate(db_session, seeded_user.id, force=True, as_of=past)

    assert [i.id for i in second] != [i.id for i in first]  # explicit force still regenerates a past period


def test_get_or_generate_for_a_past_month_regenerates_once_everything_is_dismissed(db_session, seeded_user):
    """Real bug found live: a past period's batch had already been dismissed
    (from testing before period_key existed), so the "already generated"
    check found a row and skipped regeneration, but list_active_for_user
    filtered it out as dismissed — the panel stayed permanently empty with
    no TTL to ever bring it back. Dismissing every insight from a past
    period's batch must not be a one-way door. (No flagged-category fixture
    needed — an ALL_CLEAR row is enough to exercise dismiss + regenerate.)"""
    past = _months_ago_end(2)

    first = insights.get_or_generate(db_session, seeded_user.id, as_of=past)
    for insight in first:
        insights.dismiss(db_session, seeded_user.id, insight.id)

    active = insights.get_or_generate(db_session, seeded_user.id, as_of=past)

    assert len(active) > 0
    assert all(not i.dismissed for i in active)


def test_get_or_generate_keeps_current_and_past_month_batches_independent(
    db_session, seeded_user, seeded_wallet, monkeypatch
):
    # The fixture's transactions are dated relative to the real "now", so
    # only the current-period call actually has anything to flag; the past
    # period (2 months back, before any of this fixture's data) legitimately
    # comes back ALL_CLEAR. What matters here is that the two periods get
    # separate rows and never clobber each other, not that both flag
    # something.
    calls = _mock_phrase(monkeypatch)
    _add_flagged_category(db_session, seeded_user, seeded_wallet)
    past = _months_ago_end(2)

    current_batch = insights.get_or_generate(db_session, seeded_user.id)
    past_batch = insights.get_or_generate(db_session, seeded_user.id, as_of=past)

    assert len(calls) == 1  # only the current period had a category to phrase
    assert current_batch[0].insight_type != "ALL_CLEAR"
    assert past_batch[0].insight_type == "ALL_CLEAR"
    assert {i.id for i in current_batch}.isdisjoint({i.id for i in past_batch})

    # Regenerating the current period must not touch the past period's
    # already-cached batch (or vice versa).
    insights.get_or_generate(db_session, seeded_user.id, force=True)
    assert len(calls) == 2
    still_past = insights.get_or_generate(db_session, seeded_user.id, as_of=past)
    assert len(calls) == 2  # past batch untouched
    assert {i.id for i in still_past} == {i.id for i in past_batch}


def test_dismiss_removes_insight_from_active_list(db_session, seeded_user, monkeypatch):
    _mock_phrase(monkeypatch)
    created = insights.generate_and_store(db_session, seeded_user.id)
    insight_id = created[0].id

    insights.dismiss(db_session, seeded_user.id, insight_id)

    active = AIInsightRepository(db_session).list_active_for_user(seeded_user.id, _current_period_key())
    assert insight_id not in [i.id for i in active]


def test_dismiss_unknown_insight_raises_not_found(db_session, seeded_user):
    with pytest.raises(NotFoundError):
        insights.dismiss(db_session, seeded_user.id, uuid.uuid4())


def test_dismiss_someone_elses_insight_raises_not_found(db_session, seeded_user, monkeypatch):
    _mock_phrase(monkeypatch)
    other_user = UserService(db_session).create_user(
        UserCreate(email="pf-insights-other@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    created = insights.generate_and_store(db_session, seeded_user.id)

    with pytest.raises(NotFoundError):
        insights.dismiss(db_session, other_user.id, created[0].id)
