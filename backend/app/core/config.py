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

    # Database
    database_url: str = "sqlite:///./collectiq.db"

    # PayPal - only Sandbox is allowed during the hackathon.
    # Enabling live mode must be an explicit, reviewed change.
    paypal_environment: Literal["sandbox"] = "sandbox"
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_client_id: str = ""
    paypal_client_secret: SecretStr = SecretStr("")

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


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
