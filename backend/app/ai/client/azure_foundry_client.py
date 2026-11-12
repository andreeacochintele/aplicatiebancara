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

When ANTHROPIC_API_KEY is set, chat_completion() sends the same request to
Claude (ANTHROPIC_MODEL, default claude-sonnet-5-5) instead, and wraps the
reply in the same `.choices[0].message.content` / `.usage.prompt_tokens`
shape, so no agent needs provider-specific code. Azure stays the fallback
when no Anthropic key is configured.
"""
from functools import lru_cache
from types import SimpleNamespace
from typing import Any, Iterable

from app.ai.client.config import AzureAIFoundrySettings, get_azure_ai_foundry_settings
from app.ai.observability import record_usage


class AzureFoundryNotConfiguredError(RuntimeError):
    """Raised when an agent tries to call GPT-5-mini before Azure AI Foundry
    credentials are configured. Expected during Phase 1 (AI features are not
    part of this phase) and any environment without AI configured."""


# OpenAI-style reasoning_effort (only "minimal" is used, for intent/title/
# follow-up calls) mapped onto Claude's effort levels.
_ANTHROPIC_EFFORT = {"minimal": "low", "low": "low", "medium": "medium", "high": "high"}


class AzureFoundryClient:
    """Thin wrapper around the AI provider SDKs: Claude via the Anthropic SDK
    when ANTHROPIC_API_KEY is set, otherwise GPT-5-mini on Azure AI Foundry.
    Do not add other providers here."""

    def __init__(self, settings: AzureAIFoundrySettings) -> None:
        self._settings = settings
        self._client: Any | None = None
        self._anthropic: Any | None = None

    def _get_client(self) -> Any:
        if not self._settings.is_configured:
            raise AzureFoundryNotConfiguredError(
                "No AI provider is configured. Set ANTHROPIC_API_KEY, or "
                "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and "
                "AZURE_OPENAI_DEPLOYMENT_NAME, to enable AI features."
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
        if self._settings.ANTHROPIC_API_KEY:
            response = self._anthropic_completion(list(messages), **kwargs)
        else:
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

    def _anthropic_completion(self, messages: list[dict[str, str]], reasoning_effort: str | None = None,
                              **kwargs: Any) -> Any:
        if kwargs:
            raise ValueError(f"Unsupported arguments for the Anthropic provider: {sorted(kwargs)}")
        if self._anthropic is None:
            import anthropic  # lazy import, same reason as openai above

            self._anthropic = anthropic.Anthropic(api_key=self._settings.ANTHROPIC_API_KEY)
        # Claude takes the system prompt as a separate field, not a message.
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        chat = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        response = self._anthropic.beta.messages.create(
            model=self._settings.ANTHROPIC_MODEL,
            max_tokens=16000,
            system=system,
            messages=chat,
            output_config={"effort": _ANTHROPIC_EFFORT.get(reasoning_effort or "", "medium")},
            # A safety-classifier decline is re-run on a fallback model inside the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        text = "" if response.stop_reason == "refusal" else "".join(
            block.text for block in response.content if block.type == "text"
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(
                prompt_tokens=response.usage.input_tokens, completion_tokens=response.usage.output_tokens
            ),
        )


@lru_cache
def get_azure_foundry_client() -> AzureFoundryClient:
    return AzureFoundryClient(get_azure_ai_foundry_settings())
