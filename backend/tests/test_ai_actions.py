"""Actions Agent: deterministic name matching, draft building, and the
confirm/execute path. The LLM extraction boundary is mocked — never a live
Azure call (same approach as the other AI agent tests)."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ai.actions import agent, service as action_service_module
from app.ai.actions.models import AgentAction, AgentActionStatus
from app.ai.actions.recipient_resolver import match_beneficiaries, normalize
from app.ai.actions.service import ActionService
from app.ai.orchestrator.intent import IntentCategory, _SYSTEM_PROMPT
from app.core.exceptions import ConflictError, NotFoundError
from app.payments.models import Beneficiary
from app.payments.repository import BeneficiaryRepository
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.repository import WalletRepository
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


# ---- fixtures ----


@pytest.fixture()
def sender(db_session):
    user = UserService(db_session).create_user(
        UserCreate(email="sender@example.com", password="Sup3rSecret!", first_name="Sam", last_name="Sender")
    )
    wallet = WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON", is_main=True))
    wallet.available_balance = Decimal("1000.00")
    db_session.flush()
    return user, wallet


@pytest.fixture()
def alex(db_session):
    user = UserService(db_session).create_user(
        UserCreate(email="alex@example.com", phone="+40700111222", password="Sup3rSecret!", first_name="Alex", last_name="Pop")
    )
    WalletService(db_session).create_wallet(user.id, WalletCreate(currency="RON", is_main=True))
    return user


def _add_beneficiary(db_session, owner_id, name, *, user_id=None, phone=None, iban=None):
    return BeneficiaryRepository(db_session).add(
        Beneficiary(owner_user_id=owner_id, name=name, beneficiary_user_id=user_id, phone=phone, iban=iban)
    )


# ---- recipient_resolver: pure, no DB ----


def test_normalize_folds_romanian_diacritics_and_case():
    assert normalize("  Ștefan  ĂÎÂ  ") == "stefan aia"


def _bene(name):
    return Beneficiary(owner_user_id=uuid.uuid4(), name=name)


def test_match_exact_full_name_wins_over_partials():
    pop, ionescu = _bene("Alex Pop"), _bene("Alex Ionescu")
    assert match_beneficiaries("alex pop", [pop, ionescu]) == [pop]


def test_match_single_token_prefix_matches_all_alex():
    pop, ionescu, maria = _bene("Alex Pop"), _bene("Alexandru Ionescu"), _bene("Maria D")
    assert set(match_beneficiaries("alex", [pop, ionescu, maria])) == {pop, ionescu}


def test_match_returns_empty_when_nothing_matches():
    assert match_beneficiaries("george", [_bene("Alex Pop")]) == []


# ---- prepare_phone_transfer ----


def test_prepare_happy_path_creates_a_draft_and_card(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)

    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "150", "RON", "Alex")

    assert result.action_card is not None
    assert result.action_card.amount == "150.00"
    assert result.action_card.recipient_name == "Alex Pop"
    row = db_session.get(AgentAction, result.action_card.action_id)
    assert row.status == AgentActionStatus.DRAFT
    assert row.payload["recipient_user_id"] == str(alex.id)


def test_prepare_rejects_amount_over_the_cap(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)

    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "500.01", "RON", "Alex")

    assert result.action_card is None
    assert "500 RON" in result.reply


def test_prepare_allows_exactly_the_cap(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)

    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "500", "RON", "Alex")

    assert result.action_card is not None


def test_prepare_unknown_recipient_asks_to_add_a_beneficiary(db_session, sender):
    user, _ = sender
    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "100", "RON", "Ghost")
    assert result.action_card is None
    assert "Beneficiaries" in result.reply


def test_prepare_ambiguous_recipient_asks_for_the_full_name(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    _add_beneficiary(db_session, user.id, "Alex Ionescu", phone="+40700999888")

    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "100", "RON", "Alex")

    assert result.action_card is None
    assert "Alex Ionescu" in result.reply and "Alex Pop" in result.reply


def test_prepare_rejects_insufficient_balance_with_the_real_figure(db_session, sender, alex):
    user, wallet = sender
    wallet.available_balance = Decimal("40.00")
    db_session.flush()
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)

    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "100", "RON", "Alex")

    assert result.action_card is None
    assert "40.00 RON" in result.reply


def test_prepare_rejects_non_ron(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "100", "EUR", "Alex")
    assert result.action_card is None
    assert "RON" in result.reply


def test_prepare_resolves_an_on_us_iban_beneficiary(db_session, sender, alex):
    """A beneficiary saved with only an in-app IBAN (no linked user, no
    phone) — the screenshot's "Bogdan" case — still works."""
    user, _ = sender
    alex_wallet = WalletRepository(db_session).get_by_user_and_currency(alex.id, "RON")
    _add_beneficiary(db_session, user.id, "Bogdan", iban=alex_wallet.iban)

    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "100", "RON", "Bogdan")

    assert result.action_card is not None
    row = db_session.get(AgentAction, result.action_card.action_id)
    assert row.payload["destination_wallet_id"] == str(alex_wallet.id)
    assert row.payload["recipient_user_id"] == str(alex.id)


def test_prepare_rejects_an_external_iban_beneficiary(db_session, sender):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Extern SRL", iban="RO49BANK1111222233334444")

    result = ActionService(db_session).prepare_phone_transfer(user.id, None, "100", "RON", "Extern")

    assert result.action_card is None
    assert "Payments" in result.reply


def test_confirm_executes_a_transfer_to_an_on_us_iban_beneficiary(db_session, sender, alex, monkeypatch):
    user, wallet = sender
    alex_wallet = WalletRepository(db_session).get_by_user_and_currency(alex.id, "RON")
    _add_beneficiary(db_session, user.id, "Bogdan", iban=alex_wallet.iban)
    monkeypatch.setattr(action_service_module, "screen_transfer", lambda *a, **k: _unblocked())
    card = ActionService(db_session).prepare_phone_transfer(user.id, None, "120", "RON", "Bogdan").action_card

    result = ActionService(db_session).confirm(user.id, card.action_id)

    assert result.status == AgentActionStatus.EXECUTED
    db_session.refresh(wallet)
    db_session.refresh(alex_wallet)
    assert wallet.available_balance == Decimal("880.00")
    assert alex_wallet.available_balance == Decimal("120.00")


def test_prepare_supersedes_a_previous_open_draft_in_the_same_conversation(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    conv = uuid.uuid4()
    first = ActionService(db_session).prepare_phone_transfer(user.id, conv, "100", "RON", "Alex")
    ActionService(db_session).prepare_phone_transfer(user.id, conv, "200", "RON", "Alex")

    assert db_session.get(AgentAction, first.action_card.action_id).status == AgentActionStatus.SUPERSEDED


# ---- confirm ----


def _draft(db_session, user_id, conv=None):
    return ActionService(db_session).prepare_phone_transfer(user_id, conv, "150", "RON", "Alex")


def test_confirm_executes_the_transfer_and_moves_balances(db_session, sender, alex, monkeypatch):
    user, wallet = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    monkeypatch.setattr(action_service_module, "screen_transfer", lambda *a, **k: _unblocked())
    card = _draft(db_session, user.id).action_card

    result = ActionService(db_session).confirm(user.id, card.action_id)

    assert result.status == AgentActionStatus.EXECUTED
    assert result.result_transaction_id is not None
    db_session.refresh(wallet)
    assert wallet.available_balance == Decimal("850.00")


def test_confirm_is_idempotent_on_a_second_call(db_session, sender, alex, monkeypatch):
    user, wallet = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    monkeypatch.setattr(action_service_module, "screen_transfer", lambda *a, **k: _unblocked())
    card = _draft(db_session, user.id).action_card

    first = ActionService(db_session).confirm(user.id, card.action_id)
    second = ActionService(db_session).confirm(user.id, card.action_id)

    assert first.result_transaction_id == second.result_transaction_id
    db_session.refresh(wallet)
    assert wallet.available_balance == Decimal("850.00")  # not debited twice


def test_confirm_rejects_an_expired_draft(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    card = _draft(db_session, user.id).action_card
    row = db_session.get(AgentAction, card.action_id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    with pytest.raises(ConflictError):
        ActionService(db_session).confirm(user.id, card.action_id)
    assert db_session.get(AgentAction, card.action_id).status == AgentActionStatus.EXPIRED


def test_confirm_fails_cleanly_when_the_beneficiary_was_deleted(db_session, sender, alex, monkeypatch):
    user, _ = sender
    beneficiary = _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    monkeypatch.setattr(action_service_module, "screen_transfer", lambda *a, **k: _unblocked())
    card = _draft(db_session, user.id).action_card
    BeneficiaryRepository(db_session).delete(beneficiary)

    result = ActionService(db_session).confirm(user.id, card.action_id)

    assert result.status == AgentActionStatus.FAILED
    assert result.error_code == "RECIPIENT_GONE"


def test_confirm_fails_when_balance_dropped_after_drafting(db_session, sender, alex, monkeypatch):
    user, wallet = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    monkeypatch.setattr(action_service_module, "screen_transfer", lambda *a, **k: _unblocked())
    card = _draft(db_session, user.id).action_card
    wallet.available_balance = Decimal("10.00")
    db_session.flush()

    result = ActionService(db_session).confirm(user.id, card.action_id)

    assert result.status == AgentActionStatus.FAILED
    assert result.error_code == "INSUFFICIENT_FUNDS"


def test_confirm_parks_in_needs_review_when_the_fraud_screen_blocks(db_session, sender, alex, monkeypatch):
    user, wallet = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    from app.ai.actions.fraud_screen import ScreenResult

    monkeypatch.setattr(
        action_service_module, "screen_transfer", lambda *a, **k: ScreenResult(blocked=True, reasons=["UNTRUSTED_DEVICE"])
    )
    card = _draft(db_session, user.id).action_card

    result = ActionService(db_session).confirm(user.id, card.action_id)

    assert result.status == AgentActionStatus.NEEDS_REVIEW
    db_session.refresh(wallet)
    assert wallet.available_balance == Decimal("1000.00")  # nothing moved


def test_confirm_rejects_an_action_belonging_to_another_user(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    card = _draft(db_session, user.id).action_card
    with pytest.raises(NotFoundError):
        ActionService(db_session).confirm(uuid.uuid4(), card.action_id)


def test_cancel_moves_a_draft_to_cancelled(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    card = _draft(db_session, user.id).action_card

    result = ActionService(db_session).cancel(user.id, card.action_id)

    assert result.status == AgentActionStatus.CANCELLED


def test_get_returns_the_card_data_in_any_status_for_rehydration(db_session, sender, alex):
    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    card = _draft(db_session, user.id).action_card
    ActionService(db_session).cancel(user.id, card.action_id)

    rehydrated = ActionService(db_session).get(user.id, card.action_id)

    assert rehydrated.status == AgentActionStatus.CANCELLED
    assert rehydrated.card is not None
    assert rehydrated.card.recipient_name == "Alex Pop"
    assert rehydrated.card.amount == "150.00"


def test_chat_persists_the_action_id_on_the_assistant_message(db_session, sender, alex, monkeypatch):
    from app.ai.actions import agent as actions_agent
    from app.ai.orchestrator import service as orch

    user, _ = sender
    _add_beneficiary(db_session, user.id, "Alex Pop", user_id=alex.id)
    monkeypatch.setattr(orch, "classify_intent", lambda message, history=None: IntentCategory.ACTION)
    monkeypatch.setattr(
        actions_agent, "_extract", lambda message, history: {"amount": "20", "currency": "RON", "recipient_name": "Alex"}
    )

    response = orch.OrchestratorService(db_session).chat(user.id, "trimite 20 lei lui Alex")

    assert response.action_card is not None
    messages = orch.OrchestratorService(db_session).get_conversation_messages(user.id, response.conversation_id)
    assistant_msg = next(m for m in messages if m.role == "assistant")
    assert assistant_msg.action_id == response.action_card.action_id
    # the action's live state is embedded so the UI needs no extra fetch
    assert assistant_msg.action is not None
    assert assistant_msg.action.status == AgentActionStatus.DRAFT
    assert assistant_msg.action.card is not None
    assert assistant_msg.action.card.amount == "20.00"


def _unblocked():
    from app.ai.actions.fraud_screen import ScreenResult

    return ScreenResult(blocked=False, reasons=[])


# ---- HTTP: confirm / cancel endpoints ----


def _register(client, email, phone):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "phone": phone, "password": "Sup3rSecret!", "first_name": "Test", "last_name": "User"},
    )
    assert response.status_code == 201
    return response.json()


def _auth_header(auth):
    return {"Authorization": f"Bearer {auth['tokens']['access_token']}"}


def test_confirm_endpoint_executes_the_transfer(client, db_session, monkeypatch):
    monkeypatch.setattr(action_service_module, "screen_transfer", lambda *a, **k: _unblocked())
    sender_auth = _register(client, "http-sender@example.com", "+40711000001")
    recipient_auth = _register(client, "http-alex@example.com", "+40711000002")
    sender_id = uuid.UUID(sender_auth["user"]["id"])
    recipient_id = uuid.UUID(recipient_auth["user"]["id"])

    sender_wallet = WalletService(db_session).create_wallet(sender_id, WalletCreate(currency="RON", is_main=True))
    sender_wallet.available_balance = Decimal("1000.00")
    WalletService(db_session).create_wallet(recipient_id, WalletCreate(currency="RON", is_main=True))
    _add_beneficiary(db_session, sender_id, "Alex Pop", user_id=recipient_id)
    db_session.commit()

    draft = ActionService(db_session).prepare_phone_transfer(sender_id, None, "150", "RON", "Alex")
    db_session.commit()
    action_id = draft.action_card.action_id

    response = client.post(f"/api/v1/ai/actions/{action_id}/confirm", headers=_auth_header(sender_auth))

    assert response.status_code == 200
    assert response.json()["status"] == "EXECUTED"
    assert response.json()["result_transaction_id"] is not None

    # a second confirm is idempotent, not a double transfer
    again = client.post(f"/api/v1/ai/actions/{action_id}/confirm", headers=_auth_header(sender_auth))
    assert again.json()["result_transaction_id"] == response.json()["result_transaction_id"]


def test_cancel_endpoint_then_confirm_conflicts(client, db_session, monkeypatch):
    sender_auth = _register(client, "http-sender2@example.com", "+40711000003")
    recipient_auth = _register(client, "http-alex2@example.com", "+40711000004")
    sender_id = uuid.UUID(sender_auth["user"]["id"])
    recipient_id = uuid.UUID(recipient_auth["user"]["id"])

    sw = WalletService(db_session).create_wallet(sender_id, WalletCreate(currency="RON", is_main=True))
    sw.available_balance = Decimal("1000.00")
    WalletService(db_session).create_wallet(recipient_id, WalletCreate(currency="RON", is_main=True))
    _add_beneficiary(db_session, sender_id, "Alex Pop", user_id=recipient_id)
    db_session.commit()
    draft = ActionService(db_session).prepare_phone_transfer(sender_id, None, "150", "RON", "Alex")
    db_session.commit()
    action_id = draft.action_card.action_id

    assert client.post(f"/api/v1/ai/actions/{action_id}/cancel", headers=_auth_header(sender_auth)).json()["status"] == "CANCELLED"
    assert client.post(f"/api/v1/ai/actions/{action_id}/confirm", headers=_auth_header(sender_auth)).status_code == 409


# ---- agent._parse: extraction robustness ----


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('{"amount": 150, "currency": "RON", "recipient_name": "Alex"}', {"amount": "150", "currency": "RON", "recipient_name": "Alex"}),
        ('```json\n{"amount": 50, "currency": "RON", "recipient_name": "Maria"}\n```', {"amount": "50", "currency": "RON", "recipient_name": "Maria"}),
        ("not json at all", {}),
        ('{"amount": null, "currency": "RON", "recipient_name": null}', {"amount": None, "currency": "RON", "recipient_name": None}),
    ],
)
def test_agent_parse_handles_fences_nulls_and_garbage(raw, expected):
    assert agent._parse(raw) == expected


# ---- intent wiring ----


def test_intent_has_an_action_category_and_examples():
    assert IntentCategory.ACTION.value == "action"
    assert "'Trimite 100 lei lui Alex' -> action" in _SYSTEM_PROMPT
    assert "'Cum trimit bani cuiva?' -> support" in _SYSTEM_PROMPT


def test_action_intent_never_generates_suggested_followups(db_session, monkeypatch):
    """The generic follow-up model invents capabilities the actions agent
    doesn't have — it must not run for ACTION replies."""
    from app.ai.orchestrator import service as orch

    monkeypatch.setattr(orch, "classify_intent", lambda message, history=None: IntentCategory.ACTION)
    monkeypatch.setattr(orch, "AGENT_REGISTRY", {IntentCategory.ACTION: lambda *a, **k: "«X» nu are un cont."})
    calls: list[int] = []
    monkeypatch.setattr(
        orch.OrchestratorService, "_generate_followups", lambda self, m, r: calls.append(1) or ["nope"]
    )

    response = orch.OrchestratorService(db_session).chat(uuid.uuid4(), "trimite 10 lei lui X")

    assert response.suggested_followups == []
    assert calls == []


def test_classify_intent_maps_a_transfer_request_to_action(monkeypatch):
    from app.ai.orchestrator import intent as intent_module

    class _FakeClient:
        def chat_completion(self, **kwargs):
            class _R:
                choices = [type("C", (), {"message": type("M", (), {"content": "action"})})]

            return _R()

    monkeypatch.setattr(intent_module, "get_azure_foundry_client", lambda: _FakeClient())
    assert intent_module.classify_intent("Trimite 100 lei lui Alex") == IntentCategory.ACTION


# ---- fraud_screen ----


def test_fraud_screen_blocks_on_a_burst_of_transfers(db_session):
    from app.ai.actions.fraud_screen import RAPID_TRANSFER_LIMIT, screen_transfer

    ok = screen_transfer(db_session, uuid.uuid4(), 0)
    assert ok.blocked is False

    burst = screen_transfer(db_session, uuid.uuid4(), RAPID_TRANSFER_LIMIT)
    assert burst.blocked is True
    assert "RAPID_TRANSFERS" in burst.reasons
