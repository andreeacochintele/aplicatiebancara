from datetime import datetime, timedelta, timezone

import pytest

from app.ai.credit import agent as credit_agent
from app.ai.orchestrator import service as orchestrator_service
from app.ai.orchestrator.intent import IntentCategory
from app.ai.orchestrator.models import Conversation, ConversationMessage
from app.ai.orchestrator.repository import ConversationRepository
from app.ai.orchestrator.service import HISTORY_LIMIT, OrchestratorService
from app.ai.personal_finance import agent as personal_finance_agent
from app.ai.support import agent as support_agent
from app.core.exceptions import NotFoundError
from app.users.schemas import UserCreate
from app.users.service import UserService


def _login(client, email: str, password: str = "Sup3rSecret!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.json()["tokens"]["access_token"]


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="history-user@example.com", password="Sup3rSecret!", first_name="Hist", last_name="User")
    )


def _conversation(db_session, user_id) -> Conversation:
    return ConversationRepository(db_session).create_conversation(Conversation(user_id=user_id))


def _message(user_id, conversation_id, role="user", content="m", agent_used=None) -> ConversationMessage:
    return ConversationMessage(
        user_id=user_id, conversation_id=conversation_id, role=role, content=content, agent_used=agent_used
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


# ---- repository: conversations ----


def test_repository_create_conversation_persists_it(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    conversation = repo.create_conversation(Conversation(user_id=seeded_user.id))

    assert repo.get_conversation(conversation.id).id == conversation.id


def test_repository_list_conversations_orders_by_most_recently_updated(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    now = datetime.now(timezone.utc)
    older = repo.create_conversation(Conversation(user_id=seeded_user.id, updated_at=now - timedelta(hours=1)))
    newer = repo.create_conversation(Conversation(user_id=seeded_user.id, updated_at=now))

    conversations = repo.list_conversations_for_user(seeded_user.id)

    assert [c.id for c in conversations] == [newer.id, older.id]


def test_repository_touch_conversation_updates_the_timestamp(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    conversation = repo.create_conversation(Conversation(user_id=seeded_user.id))
    later = datetime.now(timezone.utc) + timedelta(hours=1)

    repo.touch_conversation(conversation, later)

    assert repo.get_conversation(conversation.id).updated_at == later


# ---- repository: messages, scoped to one conversation ----


def test_repository_add_persists_a_message(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    repo.add(_message(seeded_user.id, conversation.id, content="hello"))

    rows = repo.list_recent_for_conversation(conversation.id, limit=10)
    assert len(rows) == 1
    assert rows[0].content == "hello"
    assert rows[0].role == "user"
    assert rows[0].agent_used is None


def test_repository_list_recent_returns_newest_first_and_respects_limit(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    for i in range(5):
        repo.add(_message(seeded_user.id, conversation.id, content=f"message {i}"))

    rows = repo.list_recent_for_conversation(conversation.id, limit=3)

    assert [row.content for row in rows] == ["message 4", "message 3", "message 2"]


def test_repository_list_recent_does_not_bleed_across_conversations(db_session, seeded_user):
    repo = ConversationRepository(db_session)
    conversation_a = _conversation(db_session, seeded_user.id)
    conversation_b = _conversation(db_session, seeded_user.id)
    repo.add(_message(seeded_user.id, conversation_a.id, content="in A"))
    repo.add(_message(seeded_user.id, conversation_b.id, content="in B"))

    rows = repo.list_recent_for_conversation(conversation_a.id, limit=10)

    assert [row.content for row in rows] == ["in A"]


# ---- storage is never pruned: list_messages_for_conversation is paginated,
# not capped at HISTORY_LIMIT, and supports loading older pages ----


def test_repository_list_messages_returns_everything_beyond_history_limit(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    total = HISTORY_LIMIT + 12
    for i in range(total):
        repo.add(_message(seeded_user.id, conversation.id, content=f"m{i}"))

    rows = repo.list_messages_for_conversation(conversation.id, limit=total + 10)

    assert len(rows) == total  # nothing pruned/deleted just because it's past HISTORY_LIMIT


def test_repository_list_messages_before_cursor_loads_an_older_page(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    base = datetime.now(timezone.utc)
    messages = []
    for i in range(5):
        message = _message(seeded_user.id, conversation.id, content=f"m{i}")
        message.created_at = base + timedelta(minutes=i)
        messages.append(message)
        repo.add(message)

    first_page = repo.list_messages_for_conversation(conversation.id, limit=2)
    assert [m.content for m in first_page] == ["m4", "m3"]

    older_page = repo.list_messages_for_conversation(conversation.id, limit=2, before=first_page[-1].created_at)
    assert [m.content for m in older_page] == ["m2", "m1"]


def test_repository_get_last_message_for_conversation(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    repo.add(_message(seeded_user.id, conversation.id, content="first"))
    repo.add(_message(seeded_user.id, conversation.id, content="last"))

    assert repo.get_last_message_for_conversation(conversation.id).content == "last"


def test_repository_get_last_message_returns_none_for_an_empty_conversation(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    assert ConversationRepository(db_session).get_last_message_for_conversation(conversation.id) is None


# ---- service.py: history is loaded (chronological, capped at HISTORY_LIMIT,
# scoped to one conversation) and persisted ----


def test_load_history_returns_chronological_order(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    repo.add(_message(seeded_user.id, conversation.id, content="first"))
    repo.add(_message(seeded_user.id, conversation.id, role="assistant", content="second", agent_used="support"))

    history = OrchestratorService(db_session)._load_history(conversation.id)

    assert history == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]


def test_load_history_is_capped_at_history_limit(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    for i in range(HISTORY_LIMIT + 5):
        repo.add(_message(seeded_user.id, conversation.id, content=f"m{i}"))

    history = OrchestratorService(db_session)._load_history(conversation.id)

    assert len(history) == HISTORY_LIMIT
    assert [h["content"] for h in history] == [f"m{i}" for i in range(5, HISTORY_LIMIT + 5)]


def test_chat_without_conversation_id_creates_a_new_conversation(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "A reply.")

    response = OrchestratorService(db_session).chat(seeded_user.id, "how do budgets work?")

    assert response.conversation_id is not None
    conversation = ConversationRepository(db_session).get_conversation(response.conversation_id)
    assert conversation.user_id == seeded_user.id


def test_chat_with_conversation_id_appends_to_that_conversation(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "A reply.")
    conversation = _conversation(db_session, seeded_user.id)

    response = OrchestratorService(db_session).chat(seeded_user.id, "how do budgets work?", conversation.id)

    assert response.conversation_id == conversation.id
    rows = ConversationRepository(db_session).list_recent_for_conversation(conversation.id, limit=10)
    assert len(rows) == 2


def test_chat_rejects_a_conversation_id_belonging_to_another_user(db_session, seeded_user, monkeypatch):
    other_user = UserService(db_session).create_user(
        UserCreate(email="other-conv-owner@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    conversation = _conversation(db_session, other_user.id)
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))

    with pytest.raises(NotFoundError):
        OrchestratorService(db_session).chat(seeded_user.id, "hi", conversation.id)


def test_chat_rejects_a_nonexistent_conversation_id(db_session, seeded_user, monkeypatch):
    import uuid as uuid_module

    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))

    with pytest.raises(NotFoundError):
        OrchestratorService(db_session).chat(seeded_user.id, "hi", uuid_module.uuid4())


def test_chat_persists_the_user_message_and_the_assistant_reply(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "A reply.")

    response = OrchestratorService(db_session).chat(seeded_user.id, "how do budgets work?")

    rows = ConversationRepository(db_session).list_recent_for_conversation(response.conversation_id, limit=10)
    assert len(rows) == 2
    assistant_row, user_row = rows[0], rows[1]
    assert user_row.role == "user"
    assert user_row.content == "how do budgets work?"
    assert user_row.agent_used is None
    assert assistant_row.role == "assistant"
    assert assistant_row.content == "A reply."
    assert assistant_row.agent_used == "support"


def test_chat_touches_the_conversations_updated_at(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "A reply.")
    conversation = _conversation(db_session, seeded_user.id)
    original_updated_at = conversation.updated_at

    OrchestratorService(db_session).chat(seeded_user.id, "hi", conversation.id)

    refreshed = ConversationRepository(db_session).get_conversation(conversation.id)
    assert refreshed.updated_at >= original_updated_at


def test_chat_persists_greeting_and_out_of_scope_turns_with_no_agent(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.GREETING))
    first = OrchestratorService(db_session).chat(seeded_user.id, "hi there")

    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.OUT_OF_SCOPE))
    OrchestratorService(db_session).chat(seeded_user.id, "write me a poem", first.conversation_id)

    rows = ConversationRepository(db_session).list_recent_for_conversation(first.conversation_id, limit=10)
    assistant_rows = [row for row in rows if row.role == "assistant"]
    assert len(assistant_rows) == 2
    assert all(row.agent_used is None for row in assistant_rows)


def test_chat_does_not_persist_anything_when_classify_intent_fails(db_session, seeded_user, monkeypatch):
    def _raise(message, history=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(orchestrator_service, "classify_intent", _raise)

    with pytest.raises(RuntimeError):
        OrchestratorService(db_session).chat(seeded_user.id, "hello")

    conversations = ConversationRepository(db_session).list_conversations_for_user(seeded_user.id)
    # A conversation is created before classify_intent runs (so a real
    # request can still be attributed to one), but it stays empty.
    assert len(conversations) == 1
    rows = ConversationRepository(db_session).list_recent_for_conversation(conversations[0].id, limit=10)
    assert rows == []


def test_chat_passes_history_to_the_intent_classifier(db_session, seeded_user, monkeypatch):
    conversation = _conversation(db_session, seeded_user.id)
    ConversationRepository(db_session).add(_message(seeded_user.id, conversation.id, content="earlier question"))
    capture: dict = {}
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT, capture))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "reply")

    OrchestratorService(db_session).chat(seeded_user.id, "new question", conversation.id)

    assert capture["message"] == "new question"
    assert capture["history"] == [{"role": "user", "content": "earlier question"}]


def test_chat_passes_history_to_the_dispatched_agent(db_session, seeded_user, monkeypatch):
    conversation = _conversation(db_session, seeded_user.id)
    ConversationRepository(db_session).add(_message(seeded_user.id, conversation.id, content="earlier question"))
    capture: dict = {}
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.PERSONAL_FINANCE))
    monkeypatch.setattr(personal_finance_agent, "_explain", _mock_explain("reply", capture))

    OrchestratorService(db_session).chat(seeded_user.id, "new question", conversation.id)

    assert capture["history"] == [{"role": "user", "content": "earlier question"}]


# ---- CRITICAL: no context bleed between two conversations for the SAME user ----


def test_no_context_bleed_between_two_conversations_for_the_same_user(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.CREDIT))
    monkeypatch.setattr(credit_agent, "_explain", _mock_explain("Your score is fine."))
    first = OrchestratorService(db_session).chat(seeded_user.id, "What's my credit score?")

    capture: dict = {}
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.PERSONAL_FINANCE, capture))
    monkeypatch.setattr(personal_finance_agent, "_explain", _mock_explain("You have 100 RON.", capture))

    # A brand new conversation for the SAME user — no conversation_id passed
    # through from `first`, so a fresh one is auto-created.
    second = OrchestratorService(db_session).chat(seeded_user.id, "What's my balance?")

    assert second.conversation_id != first.conversation_id
    assert capture["history"] == []  # nothing from the credit conversation leaked in


# ---- CRITICAL: topic switch within the SAME conversation must not stick to
# the stale agent ----


def test_topic_switch_after_a_prior_agent_is_not_routed_to_the_stale_agent(db_session, seeded_user, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.CREDIT))
    monkeypatch.setattr(credit_agent, "_explain", _mock_explain("Your score is fine."))
    first = OrchestratorService(db_session).chat(seeded_user.id, "What's my credit score?")
    assert first.intent == IntentCategory.CREDIT

    classify_capture: dict = {}
    monkeypatch.setattr(
        orchestrator_service, "classify_intent", _mock_classify(IntentCategory.PERSONAL_FINANCE, classify_capture)
    )
    pf_capture: dict = {}
    monkeypatch.setattr(personal_finance_agent, "_explain", _mock_explain("You spent 42 RON on groceries.", pf_capture))

    second = OrchestratorService(db_session).chat(
        seeded_user.id, "How much did I spend on groceries?", first.conversation_id
    )

    assert second.intent == IntentCategory.PERSONAL_FINANCE  # not stuck on CREDIT
    assert "42 RON" in second.reply

    expected_history = [
        {"role": "user", "content": "What's my credit score?"},
        {"role": "assistant", "content": first.reply},
    ]
    assert classify_capture["history"] == expected_history
    assert pf_capture["history"] == expected_history

    rows = ConversationRepository(db_session).list_recent_for_conversation(first.conversation_id, limit=10)
    assistant_rows = sorted((r for r in rows if r.role == "assistant"), key=lambda r: r.created_at)
    assert [r.agent_used for r in assistant_rows] == ["credit", "personal_finance"]


# ---- service.list_conversations() / get_conversation_messages() ----


def test_list_conversations_includes_last_message_preview(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    ConversationRepository(db_session).add(_message(seeded_user.id, conversation.id, content="first"))
    ConversationRepository(db_session).add(
        _message(seeded_user.id, conversation.id, role="assistant", content="the latest reply")
    )

    summaries = OrchestratorService(db_session).list_conversations(seeded_user.id)

    assert len(summaries) == 1
    assert summaries[0].last_message_preview == "the latest reply"


def test_list_conversations_preview_is_none_for_an_empty_conversation(db_session, seeded_user):
    _conversation(db_session, seeded_user.id)

    summaries = OrchestratorService(db_session).list_conversations(seeded_user.id)

    assert summaries[0].last_message_preview is None


def test_get_conversation_messages_returns_chronological_order(db_session, seeded_user):
    conversation = _conversation(db_session, seeded_user.id)
    repo = ConversationRepository(db_session)
    repo.add(_message(seeded_user.id, conversation.id, content="first"))
    repo.add(_message(seeded_user.id, conversation.id, role="assistant", content="second", agent_used="support"))

    messages = OrchestratorService(db_session).get_conversation_messages(seeded_user.id, conversation.id)

    assert [m.content for m in messages] == ["first", "second"]


def test_get_conversation_messages_raises_not_found_for_another_users_conversation(db_session, seeded_user):
    other_user = UserService(db_session).create_user(
        UserCreate(email="other-messages-owner@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    conversation = _conversation(db_session, other_user.id)

    with pytest.raises(NotFoundError):
        OrchestratorService(db_session).get_conversation_messages(seeded_user.id, conversation.id)


# ---- HTTP layer: POST/GET /ai/orchestrator/conversations, GET .../messages ----


def test_create_conversation_endpoint(client, db_session):
    user = UserService(db_session).create_user(
        UserCreate(email="create-conv@example.com", password="Sup3rSecret!", first_name="Create", last_name="Conv")
    )
    db_session.commit()
    token = _login(client, "create-conv@example.com")

    response = client.post("/api/v1/ai/orchestrator/conversations", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["title"] is None


def test_list_conversations_endpoint_returns_most_recently_updated_first(client, db_session, monkeypatch):
    user = UserService(db_session).create_user(
        UserCreate(email="list-conv@example.com", password="Sup3rSecret!", first_name="List", last_name="Conv")
    )
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "reply")
    first = OrchestratorService(db_session).chat(user.id, "first conversation")
    second = OrchestratorService(db_session).chat(user.id, "second conversation")
    db_session.commit()

    token = _login(client, "list-conv@example.com")
    response = client.get("/api/v1/ai/orchestrator/conversations", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body] == [str(second.conversation_id), str(first.conversation_id)]
    assert body[0]["last_message_preview"] == "reply"


def test_get_conversation_messages_endpoint_returns_the_most_recent_page_by_default(client, db_session, monkeypatch):
    user = UserService(db_session).create_user(
        UserCreate(email="conv-messages@example.com", password="Sup3rSecret!", first_name="Conv", last_name="Msg")
    )
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "reply")
    conversation_id = None
    for i in range(HISTORY_LIMIT + 3):
        response = OrchestratorService(db_session).chat(user.id, f"question {i}", conversation_id)
        conversation_id = response.conversation_id
    db_session.commit()

    token = _login(client, "conv-messages@example.com")
    response = client.get(
        f"/api/v1/ai/orchestrator/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    total_turns = HISTORY_LIMIT + 3
    assert len(body) == total_turns * 2  # every message persisted, none pruned
    assert body[0]["content"] == "question 0"
    assert body[-1]["content"] == "reply"


def test_get_conversation_messages_endpoint_supports_loading_an_older_page(client, db_session, monkeypatch):
    user = UserService(db_session).create_user(
        UserCreate(email="conv-paging@example.com", password="Sup3rSecret!", first_name="Conv", last_name="Page")
    )
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.SUPPORT))
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "reply")
    conversation_id = None
    for i in range(5):
        response = OrchestratorService(db_session).chat(user.id, f"question {i}", conversation_id)
        conversation_id = response.conversation_id
    db_session.commit()

    token = _login(client, "conv-paging@example.com")
    first_page = client.get(
        f"/api/v1/ai/orchestrator/conversations/{conversation_id}/messages?limit=4",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    oldest_in_first_page = first_page[0]["created_at"]

    older_page = client.get(
        f"/api/v1/ai/orchestrator/conversations/{conversation_id}/messages?limit=4&before={oldest_in_first_page}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert len(older_page) >= 1
    assert older_page[-1]["created_at"] < oldest_in_first_page


def test_get_conversation_messages_endpoint_rejects_another_users_conversation(client, db_session):
    owner = UserService(db_session).create_user(
        UserCreate(email="conv-owner@example.com", password="Sup3rSecret!", first_name="Owner", last_name="Conv")
    )
    intruder = UserService(db_session).create_user(
        UserCreate(email="conv-intruder@example.com", password="Sup3rSecret!", first_name="Intruder", last_name="Conv")
    )
    conversation = _conversation(db_session, owner.id)
    db_session.commit()

    token = _login(client, "conv-intruder@example.com")
    response = client.get(
        f"/api/v1/ai/orchestrator/conversations/{conversation.id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_chat_endpoint_without_conversation_id_creates_one(client, db_session, monkeypatch):
    user = UserService(db_session).create_user(
        UserCreate(email="chat-endpoint@example.com", password="Sup3rSecret!", first_name="Chat", last_name="Endpoint")
    )
    db_session.commit()
    monkeypatch.setattr(orchestrator_service, "classify_intent", _mock_classify(IntentCategory.GREETING))

    token = _login(client, "chat-endpoint@example.com")
    response = client.post(
        "/api/v1/ai/orchestrator/chat", headers={"Authorization": f"Bearer {token}"}, json={"message": "hi"}
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"]


def test_conversation_endpoints_require_authentication(client):
    assert client.post("/api/v1/ai/orchestrator/conversations").status_code == 401
    assert client.get("/api/v1/ai/orchestrator/conversations").status_code == 401
    import uuid as uuid_module

    assert client.get(f"/api/v1/ai/orchestrator/conversations/{uuid_module.uuid4()}/messages").status_code == 401
