"""Application configuration, loaded from environment variables / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Banking App API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+psycopg://banking:banking@localhost:5432/banking"

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production-please-use-a-long-random-value"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SESSION_INACTIVITY_TIMEOUT_MINUTES: int = 5

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Azure AI Foundry (GPT-5-mini) — optional, AI features degrade gracefully if unset
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_API_VERSION: str | None = None
    AZURE_OPENAI_DEPLOYMENT_NAME: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
