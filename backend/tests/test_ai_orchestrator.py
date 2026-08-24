import uuid

import pytest

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.credit.agent import handle as credit_handle
from app.ai.orchestrator import service as orchestrator_service
from app.ai.orchestrator.intent import IntentCategory, _parse_category
from app.ai.orchestrator.registry import AGENT_REGISTRY
from app.ai.orchestrator.service import OrchestratorService
from app.ai.personal_finance.agent import handle as personal_finance_handle
from app.ai.support.agent import handle as support_handle


def test_parse_category_matches_each_known_value():
    for category in IntentCategory:
        assert _parse_category(f"  {category.value}  ") == category


def test_parse_category_falls_back_to_out_of_scope_on_unrecognized_text():
    assert _parse_category("i have no idea what you mean") == IntentCategory.OUT_OF_SCOPE


def test_registry_has_no_fraud_entry_and_exactly_the_three_routable_agents():
    assert set(AGENT_REGISTRY.keys()) == {
        IntentCategory.PERSONAL_FINANCE,
        IntentCategory.CREDIT,
        IntentCategory.SUPPORT,
    }


def test_agent_stubs_return_a_mock_string_reply(db_session):
    user_id = uuid.uuid4()
    for handle in (personal_finance_handle, credit_handle, support_handle):
        reply = handle("any message", user_id, db_session)
        assert isinstance(reply, str)
        assert reply


def test_chat_propagates_azure_not_configured_instead_of_swallowing_it(db_session, monkeypatch):
    # Simulated at the classify_intent seam rather than by unsetting env vars:
    # get_azure_foundry_client()/get_azure_ai_foundry_settings() are
    # lru_cache'd process-wide, so env-var patching here wouldn't reliably
    # affect them, and a developer's real local .env (if configured) would
    # otherwise make this test hit the live Azure endpoint.
    def _raise_not_configured(message: str) -> IntentCategory:
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    monkeypatch.setattr(orchestrator_service, "classify_intent", _raise_not_configured)
    with pytest.raises(AzureFoundryNotConfiguredError):
        OrchestratorService(db_session).chat(uuid.uuid4(), "hello")


def test_chat_answers_greeting_directly_without_touching_the_registry(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", lambda message: IntentCategory.GREETING)
    response = OrchestratorService(db_session).chat(uuid.uuid4(), "hi there")
    assert response.intent == IntentCategory.GREETING
    assert response.reply


def test_chat_answers_out_of_scope_directly_without_touching_the_registry(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", lambda message: IntentCategory.OUT_OF_SCOPE)
    response = OrchestratorService(db_session).chat(uuid.uuid4(), "write me a poem")
    assert response.intent == IntentCategory.OUT_OF_SCOPE
    assert response.reply


@pytest.mark.parametrize(
    "intent",
    [IntentCategory.PERSONAL_FINANCE, IntentCategory.CREDIT, IntentCategory.SUPPORT],
)
def test_chat_routes_each_routable_intent_to_its_agent_stub(db_session, monkeypatch, intent):
    monkeypatch.setattr(orchestrator_service, "classify_intent", lambda message: intent)
    response = OrchestratorService(db_session).chat(uuid.uuid4(), "some message")
    assert response.intent == intent
    assert response.reply == AGENT_REGISTRY[intent]("some message", uuid.uuid4(), db_session)
