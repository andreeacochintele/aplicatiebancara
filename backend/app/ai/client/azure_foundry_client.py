"""Shared Azure AI Foundry (GPT-5-mini) client abstraction.

Every future agent (Orchestrator, Personal Finance, Credit, Fraud
Investigation) must go through this single client rather than instantiating
its own connection — this is the "Shared Azure GPT-5-mini Client" box in the
conceptual architecture:

    AI Agents -> Shared Azure GPT-5-mini Client -> Azure AI Foundry

The client is intentionally thin: agents own their prompts/tool schemas, this
module only owns the transport. Nothing here touches the database — agents
reach data exclusively through tools that call backend services
(Agent -> Tool -> Backend Service -> Database), never directly.

Instantiation is lazy: importing this module, or booting the app, never
requires Azure credentials. Only calling `chat_completion()` does.

Uses the plain `openai.OpenAI` client pointed at Azure AI Foundry's
`/openai/v1/` compatibility route — NOT `openai.AzureOpenAI` (which targets
the classic `<resource>.openai.azure.com/openai/deployments/{name}/...`
shape some Foundry resource tiers, including academic-tier ones, don't
expose at all — confirmed by a live 404 against this project's resource),
and NOT the `azure-ai-inference` package (Microsoft deprecated it in favor
of this same `/openai/v1/` route; it's retiring 2026-08-26). `/openai/v1/`
is implicitly versioned — no api-version query param — and accepts a plain
API key as a Bearer token, so `chat.completions.create()` behaves exactly
as before with no response-shape adapter needed.

Confirmed live against the real resource: this deployment
(gpt-5-mini-2025-08-07) is a reasoning model and rejects any non-default
`temperature` with a 400 — callers must not pass `temperature=` at all.
"""
from functools import lru_cache
from typing import Any, Iterable

from app.ai.client.config import AzureAIFoundrySettings, get_azure_ai_foundry_settings
from app.ai.observability import record_usage


class AzureFoundryNotConfiguredError(RuntimeError):
    """Raised when an agent tries to call GPT-5-mini before Azure AI Foundry
    credentials are configured. Expected during Phase 1 (AI features are not
    part of this phase) and any environment without AI configured."""


class AzureFoundryClient:
    """Thin wrapper around the OpenAI SDK, pinned to a single GPT-5-mini
    deployment on Azure AI Foundry. Do not add other providers here."""

    def __init__(self, settings: AzureAIFoundrySettings) -> None:
        self._settings = settings
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if not self._settings.is_configured:
            raise AzureFoundryNotConfiguredError(
                "Azure AI Foundry is not configured. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT_NAME to enable "
                "AI features."
            )
        if self._client is None:
            from openai import OpenAI  # lazy import: app boots without `openai` needing valid config

            endpoint = self._settings.AZURE_OPENAI_ENDPOINT.rstrip("/")
            self._client = OpenAI(
                base_url=f"{endpoint}/openai/v1/",
                api_key=self._settings.AZURE_OPENAI_API_KEY,
            )
        return self._client

    def chat_completion(self, messages: Iterable[dict[str, str]], **kwargs: Any) -> Any:
        """Send a chat-completion request to the GPT-5-mini deployment.

        `kwargs` are passed through to the underlying SDK call (e.g. `tools`,
        `temperature`) so agent code doesn't need its own transport logic.
        """
        client = self._get_client()
        response = client.chat.completions.create(
            model=self._settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=list(messages),
            **kwargs,
        )
        # Reports token usage to ai/observability.py's llm_call log event —
        # see record_usage()'s docstring for why this lives here rather than
        # at every call site.
        record_usage(getattr(response, "usage", None))
        return response


@lru_cache
def get_azure_foundry_client() -> AzureFoundryClient:
    return AzureFoundryClient(get_azure_ai_foundry_settings())
