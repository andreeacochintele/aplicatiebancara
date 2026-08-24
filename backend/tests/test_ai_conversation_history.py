import pytest

from app.ai.credit import agent as credit_agent
from app.ai.orchestrator import service as orchestrator_service
from app.ai.orchestrator.intent import IntentCategory
from app.ai.orchestrator.models import ConversationMessage
from app.ai.orchestrator.repository import ConversationRepository
from app.ai.orchestrator.service import HISTORY_LIMIT, OrchestratorService
from app.ai.personal_finance import agent as personal_finance_agent
from app.ai.support import agent as support_agent
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="history-user@example.com", password="Sup3rSecret!", first_name="Hist", last_name="User")
    )


def _mock_classify(intent: IntentCategory, capture: dict | None = None):
    def _classify(message, history=None):
        if capture is not None:
            capture["message"] = message
            capture["history"] = history
        return intent

    return _classify


def _mock_explain(reply: str, capture: dict | None = None):
    def _explain(message, data_summary, history=None):
        if capture is not None:
            capture["message"] = message
            capture["history"] = history
        return reply

    return _explain


# ---- repository: plain append-only log, newest-first, limit-respecting ----


def test_repository_add_persists_a_message(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    repo.add(ConversationMessage(user_id=seeded_user.id, role="user", content="hello", agent_used=None))

    rows = repo.list_recent_for_user(seeded_user.id, limit=10)
    assert len(rows) == 1
    assert rows[0].content == "hello"
    assert rows[0].role == "user"
    assert rows[0].agent_used is None


def test_repository_list_recent_returns_newest_first_and_respects_limit(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    for i in range(5):
        repo.add(ConversationMessage(user_id=seeded_user.id, role="user", content=f"message {i}", agent_used=None))

    rows = repo.list_recent_for_user(seeded_user.id, limit=3)

    assert [row.content for row in rows] == ["message 4", "message 3", "message 2"]


def test_repository_only_returns_messages_for_the_given_user(db_session, seeded_user):
    other_user = UserService(db_session).create_user(
        UserCreate(email="other-history-user@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    repo = ConversationRepository(db_session)
    repo.add(ConversationMessage(user_id=seeded_user.id, role="user", content="mine", agent_used=None))
    repo.add(ConversationMessage(user_id=other_user.id, role="user", content="not mine", agent_used=None))

    rows = repo.list_recent_for_user(seeded_user.id, limit=10)

    assert [row.content for row in rows] == ["mine"]


# ---- service.py: history is loaded (chronological, capped at HISTORY_LIMIT) and persisted ----


def test_load_history_returns_chronological_order(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    repo.add(ConversationMessage(user_id=seeded_user.id, role="user", content="first", agent_used=None))
    repo.add(ConversationMessage(user_id=seeded_user.id, role="assistant", content="second", agent_used="support"))

    history = OrchestratorService(db_session)._load_history(seeded_user.id)

    assert history == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]


def test_load_history_is_capped_at_history_limit(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    for i in range(HISTORY_LIMIT + 5):
        repo.add(ConversationMessage(user_id=seeded_user.id, role="user", content=f"m{i}", agent_used=None))

    history = OrchestratorService(db_session)._load_history(seeded_user.id)

    assert len(history) == HISTORY_LIMIT
    # Still the most recent HISTORY_LIMIT, in chronological order.
    assert [h["content"] for h in history] == [f"m{i}" for i in range(5, HISTORY_LIMIT + 5)]


def test_chat_persists_the_user_message_and_the_assistant_reply(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "A reply.")

    OrchestratorService(db_session).chat(seeded_user.id, "how do budgets work?")

    rows = ConversationRepository(db_session).list_recent_for_user(seeded_user.id, limit=10)
    assert len(rows) == 2
    assistant_row, user_row = rows[0], rows[1]
    assert user_row.role == "user"
    assert user_row.content == "how do budgets work?"
    assert user_row.agent_used is None
    assert assistant_row.role == "assistant"
    assert assistant_row.content == "A reply."
    assert assistant_row.agent_used == "support"


def test_chat_persists_greeting_and_out_of_scope_turns_with_no_agent(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.GREETING))
    OrchestratorService(db_session).chat(seeded_user.id, "hi there")

    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.OUT_OF_SCOPE))
    OrchestratorService(db_session).chat(seeded_user.id, "write me a poem")

    rows = ConversationRepository(db_session).list_recent_for_user(seeded_user.id, limit=10)
    assistant_rows = [row for row in rows if row.role == "assistant"]
    assert len(assistant_rows) == 2
    assert all(row.agent_used is None for row in assistant_rows)


def test_chat_does_not_persist_anything_when_classify_intent_fails(db_session, seeded_user, monkeypatch):
    def _raise(message, history=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(orchestrator_service, "classify_intent", _raise)

    with pytest.raises(RuntimeError):
        OrchestratorService(db_session).chat(seeded_user.id, "hello")

    rows = ConversationRepository(db_session).list_recent_for_user(seeded_user.id, limit=10)
    assert rows == []


def test_chat_passes_history_to_the_intent_classifier(db_session, seeded_user, monkeypatch):
    ConversationRepository(db_session).add(
        ConversationMessage(user_id=seeded_user.id, role="user", content="earlier question", agent_used=None)
    )
    capture: dict = {}
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT, capture))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "reply")

    OrchestratorService(db_session).chat(seeded_user.id, "new question")

    assert capture["message"] == "new question"
    assert capture["history"] == [{"role": "user", "content": "earlier question"}]


def test_chat_passes_history_to_the_dispatched_agent(db_session, seeded_user, monkeypatch):
    ConversationRepository(db_session).add(
        ConversationMessage(user_id=seeded_user.id, role="user", content="earlier question", agent_used=None)
    )
    capture: dict = {}
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.PERSONAL_FINANCE))
    monkeypatch.setattr(personal_finance_agent, "_explain", _mock_explain("reply", capture))

    OrchestratorService(db_session).chat(seeded_user.id, "new question")

    assert capture["history"] == [{"role": "user", "content": "earlier question"}]


# ---- CRITICAL: topic switch after a prior agent must not stick to the stale agent ----


def test_topic_switch_after_a_prior_agent_is_not_routed_to_the_stale_agent(db_session, seeded_user, monkeypatch):
    # Turn 1: a credit question, correctly handled by the credit agent.
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.CREDIT))
    monkeypatch.setattr(credit_agent, "_explain", _mock_explain("Your score is fine."))
    first = OrchestratorService(db_session).chat(seeded_user.id, "What's my credit score?")
    assert first.intent == IntentCategory.CREDIT

    # Turn 2: an unrelated personal_finance question. classify_intent is
    # mocked to return PERSONAL_FINANCE for *this* call specifically — this
    # proves nothing in service.py/registry.py overrides that decision with
    # the previous turn's agent just because history (containing a prior
    # credit exchange) is present. A real classifier's own judgment on this
    # exact scenario is covered separately by the live smoke test.
    classify_capture: dict = {}
    monkeypatch.setattr(
        orchestrator_service, "classify_intent", _mock_classify(IntentCategory.PERSONAL_FINANCE, classify_capture)
    )
    pf_capture: dict = {}
    monkeypatch.setattr(personal_finance_agent, "_explain", _mock_explain("You spent 42 RON on groceries.", pf_capture))

    second = OrchestratorService(db_session).chat(seeded_user.id, "How much did I spend on groceries?")

    assert second.intent == IntentCategory.PERSONAL_FINANCE  # not stuck on CREDIT
    assert "42 RON" in second.reply

    # The classifier and the dispatched agent both saw turn 1's real Q&A as
    # history for turn 2 — proving history is passed through, not that it
    # was ignored entirely (which would trivially "solve" the sticky bug).
    expected_history = [
        {"role": "user", "content": "What's my credit score?"},
        {"role": "assistant", "content": first.reply},
    ]
    assert classify_capture["history"] == expected_history
    assert pf_capture["history"] == expected_history

    # And the persisted log reflects both turns with the correct agent each.
    rows = ConversationRepository(db_session).list_recent_for_user(seeded_user.id, limit=10)
    assistant_rows = sorted((r for r in rows if r.role == "assistant"), key=lambda r: r.created_at)
    assert [r.agent_used for r in assistant_rows] == ["credit", "personal_finance"]
