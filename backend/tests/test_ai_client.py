import pytest

from app.ai.client.azure_foundry_client import AzureFoundryClient, AzureFoundryNotConfiguredError
from app.ai.client.config import AzureAIFoundrySettings


def _settings(**overrides) -> AzureAIFoundrySettings:
    defaults = dict(
        AZURE_OPENAI_ENDPOINT="https://example-resource.services.ai.azure.com",
        AZURE_OPENAI_API_KEY="test-key",
        AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-mini",
        ANTHROPIC_API_KEY=None,
    )
    defaults.update(overrides)
    return AzureAIFoundrySettings(**defaults)


class _FakeCompletions:
    def __init__(self) -> None:
        self.create_kwargs: dict | None = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return "fake-response"


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAI:
    """Stand-in for openai.OpenAI, capturing how it was constructed."""

    last_instance: "_FakeOpenAI | None" = None

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.chat = _FakeChat()
        _FakeOpenAI.last_instance = self


def test_chat_completion_raises_when_not_configured():
    client = AzureFoundryClient(_settings(AZURE_OPENAI_API_KEY=None))
    with pytest.raises(AzureFoundryNotConfiguredError):
        client.chat_completion(messages=[{"role": "user", "content": "hi"}])


def test_chat_completion_points_the_openai_client_at_the_v1_route_with_no_api_version(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)
    client = AzureFoundryClient(_settings())

    result = client.chat_completion(messages=[{"role": "user", "content": "hi"}], temperature=0)

    fake = _FakeOpenAI.last_instance
    assert result == "fake-response"
    assert fake.base_url == "https://example-resource.services.ai.azure.com/openai/v1/"
    assert fake.api_key == "test-key"
    assert fake.chat.completions.create_kwargs == {
        "model": "gpt-5-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0,
    }


def test_chat_completion_strips_a_trailing_slash_from_the_endpoint_to_avoid_a_double_slash(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)
    client = AzureFoundryClient(_settings(AZURE_OPENAI_ENDPOINT="https://example-resource.services.ai.azure.com/"))

    client.chat_completion(messages=[])

    assert _FakeOpenAI.last_instance.base_url == "https://example-resource.services.ai.azure.com/openai/v1/"


# ---- token usage reporting: chat_completion() forwards response.usage to
# ai/observability.py's record_usage() — see that module for why (a
# `with timed_event("llm_call", ...):` block can't see a local variable
# created inside its own body any other way).


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def test_chat_completion_reports_the_response_usage_to_observability(monkeypatch):
    fake_usage = _FakeUsage(prompt_tokens=23, completion_tokens=141)

    class _FakeResponseWithUsage:
        def __init__(self, usage) -> None:
            self.usage = usage

    class _FakeCompletionsWithUsage:
        def create(self, **kwargs):
            return _FakeResponseWithUsage(fake_usage)

    class _FakeOpenAIWithUsage:
        def __init__(self, *, base_url: str, api_key: str) -> None:
            self.chat = type("Chat", (), {"completions": _FakeCompletionsWithUsage()})()

    monkeypatch.setattr("openai.OpenAI", _FakeOpenAIWithUsage)
    recorded: dict = {}
    monkeypatch.setattr("app.ai.client.azure_foundry_client.record_usage", lambda u: recorded.update(usage=u))

    AzureFoundryClient(_settings()).chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert recorded["usage"] is fake_usage


def test_chat_completion_reports_none_when_the_response_has_no_usage_attribute(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)
    recorded: dict = {}
    monkeypatch.setattr("app.ai.client.azure_foundry_client.record_usage", lambda u: recorded.update(usage=u))

    AzureFoundryClient(_settings()).chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert recorded["usage"] is None


# ---- Anthropic provider: used instead of Azure whenever ANTHROPIC_API_KEY is set


class _FakeAnthropicMessages:
    def __init__(self, response) -> None:
        self.response = response
        self.create_kwargs: dict | None = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return self.response


class _FakeAnthropic:
    last_instance: "_FakeAnthropic | None" = None
    response = None

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key
        self.beta = type("Beta", (), {})()
        self.beta.messages = _FakeAnthropicMessages(_FakeAnthropic.response)
        _FakeAnthropic.last_instance = self


def _claude_response(stop_reason="end_turn", text="Salut!"):
    block = lambda t, **kw: type("Block", (), {"type": t, **kw})()  # noqa: E731
    return type("Message", (), {
        "stop_reason": stop_reason,
        "content": [block("thinking", thinking=""), block("text", text=text)],
        "usage": type("Usage", (), {"input_tokens": 12, "output_tokens": 34})(),
    })()


def test_anthropic_key_routes_to_claude_and_returns_the_openai_shape(monkeypatch):
    _FakeAnthropic.response = _claude_response()
    monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropic)
    recorded: dict = {}
    monkeypatch.setattr("app.ai.client.azure_foundry_client.record_usage", lambda u: recorded.update(usage=u))
    client = AzureFoundryClient(_settings(ANTHROPIC_API_KEY="sk-ant-test", AZURE_OPENAI_API_KEY=None))

    result = client.chat_completion(
        messages=[{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}],
        reasoning_effort="minimal",
    )

    sent = _FakeAnthropic.last_instance.beta.messages.create_kwargs
    assert _FakeAnthropic.last_instance.api_key == "sk-ant-test"
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["system"] == "Be brief."
    assert sent["messages"] == [{"role": "user", "content": "hi"}]
    assert sent["output_config"] == {"effort": "low"}
    assert result.choices[0].message.content == "Salut!"
    assert (recorded["usage"].prompt_tokens, recorded["usage"].completion_tokens) == (12, 34)


def test_anthropic_refusal_returns_empty_content(monkeypatch):
    _FakeAnthropic.response = _claude_response(stop_reason="refusal", text="partial")
    monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropic)
    client = AzureFoundryClient(_settings(ANTHROPIC_API_KEY="sk-ant-test"))

    result = client.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert result.choices[0].message.content == ""
    assert _FakeAnthropic.last_instance.beta.messages.create_kwargs["output_config"] == {"effort": "medium"}


def test_anthropic_rejects_openai_only_arguments(monkeypatch):
    _FakeAnthropic.response = _claude_response()
    monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropic)
    client = AzureFoundryClient(_settings(ANTHROPIC_API_KEY="sk-ant-test"))

    with pytest.raises(ValueError):
        client.chat_completion(messages=[{"role": "user", "content": "hi"}], temperature=0)
