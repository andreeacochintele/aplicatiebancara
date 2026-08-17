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
"""
from functools import lru_cache
from typing import Any, Iterable

from app.ai.client.config import AzureAIFoundrySettings, get_azure_ai_foundry_settings


class AzureFoundryNotConfiguredError(RuntimeError):
    """Raised when an agent tries to call GPT-5-mini before Azure AI Foundry
    credentials are configured. Expected during Phase 1 (AI features are not
    part of this phase) and any environment without AI configured."""


class AzureFoundryClient:
    """Thin wrapper around the Azure OpenAI SDK, pinned to a single GPT-5-mini
    deployment on Azure AI Foundry. Do not add other providers here."""

    def __init__(self, settings: AzureAIFoundrySettings) -> None:
        self._settings = settings
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if not self._settings.is_configured:
            raise AzureFoundryNotConfiguredError(
                "Azure AI Foundry is not configured. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION and "
                "AZURE_OPENAI_DEPLOYMENT_NAME to enable AI features."
            )
        if self._client is None:
            from openai import AzureOpenAI  # lazy import: app boots without `openai` needing valid config

            self._client = AzureOpenAI(
                azure_endpoint=self._settings.AZURE_OPENAI_ENDPOINT,
                api_key=self._settings.AZURE_OPENAI_API_KEY,
                api_version=self._settings.AZURE_OPENAI_API_VERSION,
            )
        return self._client

    def chat_completion(self, messages: Iterable[dict[str, str]], **kwargs: Any) -> Any:
        """Send a chat-completion request to the GPT-5-mini deployment.

        `kwargs` are passed through to the underlying SDK call (e.g. `tools`,
        `temperature`) so agent code doesn't need its own transport logic.
        """
        client = self._get_client()
        return client.chat.completions.create(
            model=self._settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=list(messages),
            **kwargs,
        )


@lru_cache
def get_azure_foundry_client() -> AzureFoundryClient:
    return AzureFoundryClient(get_azure_ai_foundry_settings())
