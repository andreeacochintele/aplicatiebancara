"""Azure AI Foundry configuration.

GPT-5-mini deployed on Azure AI Foundry is the ONLY model this application is
allowed to talk to. Do not add settings for other providers (OpenAI direct,
Anthropic, Gemini, local models) — see backend/app/ai/README.md.

All values are optional so the app boots without them configured; the client
only raises when an agent actually tries to call the model.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AzureAIFoundrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_API_VERSION: str | None = None
    AZURE_OPENAI_DEPLOYMENT_NAME: str | None = None

    @property
    def is_configured(self) -> bool:
        return all(
            [
                self.AZURE_OPENAI_ENDPOINT,
                self.AZURE_OPENAI_API_KEY,
                self.AZURE_OPENAI_API_VERSION,
                self.AZURE_OPENAI_DEPLOYMENT_NAME,
            ]
        )


@lru_cache
def get_azure_ai_foundry_settings() -> AzureAIFoundrySettings:
    return AzureAIFoundrySettings()
