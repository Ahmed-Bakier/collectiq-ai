"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder prefix used in .env.example; values starting with it are treated as unset.
PLACEHOLDER_PREFIX = "your-"


class Settings(BaseSettings):
    """Typed application settings. Secrets are never exposed in plain text."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "CollectIQ AI"
    app_env: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:5173"

    # Timezone that defines "today" for due-date calculations.
    # The Sandbox merchant account is US-based.
    business_timezone: str = "America/Los_Angeles"

    # Database
    database_url: str = "sqlite:///./collectiq.db"

    # PayPal - only Sandbox is allowed during the hackathon.
    # Enabling live mode must be an explicit, reviewed change.
    paypal_environment: Literal["sandbox"] = "sandbox"
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_client_id: str = ""
    paypal_client_secret: SecretStr = SecretStr("")

    # Email of the Sandbox business account that issues demo invoices.
    paypal_sandbox_invoicer_email: str | None = None

    # Webhook ID from the PayPal Developer Dashboard (needed to verify webhook signatures).
    paypal_webhook_id: str | None = None

    # AI provider (any OpenAI-compatible Chat Completions API).
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_model: str = "gemini-3.6-flash"
    llm_api_key: SecretStr = SecretStr("")
    llm_reasoning_effort: str | None = None

    # Background autopilot schedule in minutes (0 = disabled; use "Run now" instead).
    autopilot_interval_minutes: int = 0

    # Optional second model on the same provider, used once when the primary hits a rate limit or error.
    llm_fallback_model: str | None = None

    # Max AI requests (assistant, autopilot, AI rewrite) per client IP per hour; 0 = unlimited.
    ai_rate_limit_per_hour: int = 0

    # Built frontend (Vite dist) served by the backend in production; unset in development.
    frontend_dist_dir: str | None = None

    @property
    def paypal_credentials_configured(self) -> bool:
        """Return True when real (non-placeholder) PayPal credentials are present."""
        client_id = self.paypal_client_id.strip()
        client_secret = self.paypal_client_secret.get_secret_value().strip()
        return (
            bool(client_id)
            and bool(client_secret)
            and not client_id.startswith(PLACEHOLDER_PREFIX)
            and not client_secret.startswith(PLACEHOLDER_PREFIX)
        )

    @property
    def llm_configured(self) -> bool:
        """Return True when a real (non-placeholder) LLM API key is present."""
        key = self.llm_api_key.get_secret_value().strip()
        return bool(key) and not key.startswith(PLACEHOLDER_PREFIX)


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
