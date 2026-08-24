import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from openai import APIConnectionError

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.credit import agent as credit_agent
from app.ai.orchestrator import router as orchestrator_router
from app.ai.orchestrator import service as orchestrator_service
from app.ai.orchestrator.intent import IntentCategory, _parse_category
from app.ai.orchestrator.registry import AGENT_REGISTRY
from app.ai.orchestrator.schemas import OrchestratorChatRequest
from app.ai.orchestrator.service import OrchestratorService
from app.ai.personal_finance import agent as personal_finance_agent
from app.ai.support import agent as support_agent


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


def test_chat_propagates_azure_not_configured_instead_of_swallowing_it(db_session, monkeypatch):
    # Simulated at the classify_intent seam rather than by unsetting env vars:
    # get_azure_foundry_client()/get_azure_ai_foundry_settings() are
    # lru_cache'd process-wide, so env-var patching here wouldn't reliably
    # affect them, and a developer's real local .env (if configured) would
    # otherwise make this test hit the live Azure endpoint.
    def _raise_not_configured(message: str, history: list[dict[str, str]] | None = None) -> IntentCategory:
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    monkeypatch.setattr(orchestrator_service, "classify_intent", _raise_not_configured)
    with pytest.raises(AzureFoundryNotConfiguredError):
        OrchestratorService(db_session).chat(uuid.uuid4(), "hello")


def test_chat_answers_greeting_directly_without_touching_the_registry(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "classify_intent", lambda message, history=None: IntentCategory.GREETING)
    response = OrchestratorService(db_session).chat(uuid.uuid4(), "hi there")
    assert response.intent == IntentCategory.GREETING
    assert response.reply


def test_chat_answers_out_of_scope_directly_without_touching_the_registry(db_session, monkeypatch):
    monkeypatch.setattr(
        orchestrator_service, "classify_intent", lambda message, history=None: IntentCategory.OUT_OF_SCOPE
    )
    response = OrchestratorService(db_session).chat(uuid.uuid4(), "write me a poem")
    assert response.intent == IntentCategory.OUT_OF_SCOPE
    assert response.reply


@pytest.mark.parametrize(
    "intent",
    [IntentCategory.PERSONAL_FINANCE, IntentCategory.CREDIT, IntentCategory.SUPPORT],
)
def test_chat_routes_each_routable_intent_to_its_agent_handler(db_session, monkeypatch, intent):
    # Every registered agent's handle() makes its own azure_foundry_client
    # call (see each agent.py's _explain) — mocked here too so this stays a
    # routing test, not a live-network test; each agent's own test file
    # covers that call's behavior.
    monkeypatch.setattr(
        personal_finance_agent, "_explain", lambda message, data_summary, history=None: "mocked explanation"
    )
    monkeypatch.setattr(credit_agent, "_explain", lambda message, data_summary, history=None: "mocked explanation")
    monkeypatch.setattr(support_agent, "_explain", lambda message, history=None: "mocked explanation")
    monkeypatch.setattr(orchestrator_service, "classify_intent", lambda message, history=None: intent)
    response = OrchestratorService(db_session).chat(uuid.uuid4(), "some message")
    assert response.intent == intent
    assert response.reply == AGENT_REGISTRY[intent]("some message", uuid.uuid4(), db_session)


def test_chat_route_maps_azure_api_errors_to_a_clean_503_without_leaking_details(db_session, monkeypatch):
    # Covers credentials-configured-but-the-call-fails (wrong deployment name,
    # auth rejected, Azure-side outage, ...) — distinct from
    # AzureFoundryNotConfiguredError (credentials missing entirely). Found via
    # a real E2E check against this env's .env, which has Azure configured
    # but pointing at a deployment that 404s.
    def _raise_api_error(self, user_id, message):
        raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))

    monkeypatch.setattr(OrchestratorService, "chat", _raise_api_error)

    with pytest.raises(HTTPException) as exc_info:
        orchestrator_router.chat(
            OrchestratorChatRequest(message="hello"),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=db_session,
        )

    assert exc_info.value.status_code == 503
    assert "temporarily unavailable" in exc_info.value.detail
    assert "example.invalid" not in exc_info.value.detail
