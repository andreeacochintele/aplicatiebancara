import pytest

from app.ai.client.azure_foundry_client import AzureFoundryClient, AzureFoundryNotConfiguredError
from app.ai.client.config import AzureAIFoundrySettings


def _settings(**overrides) -> AzureAIFoundrySettings:
    defaults = dict(
        AZURE_OPENAI_ENDPOINT="https://example-resource.services.ai.azure.com",
        AZURE_OPENAI_API_KEY="test-key",
        AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-mini",
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
