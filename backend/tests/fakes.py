"""Shared test helpers. These fakes never contact the real PayPal API."""

import httpx

from app.core.config import Settings

FAKE_ACCESS_TOKEN = "fake-access-token"
FAKE_APP_ID = "APP-TEST-123"


def make_settings(**overrides: object) -> Settings:
    """Build settings with fake credentials, ignoring the local .env file."""
    values: dict[str, object] = {
        "paypal_client_id": "test-client-id",
        "paypal_client_secret": "test-client-secret",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def token_ok_handler(request: httpx.Request) -> httpx.Response:
    """Simulate a successful PayPal token response."""
    return httpx.Response(
        200,
        json={
            "access_token": FAKE_ACCESS_TOKEN,
            "token_type": "Bearer",
            "app_id": FAKE_APP_ID,
            "expires_in": 32400,
        },
    )


def token_rejected_handler(request: httpx.Request) -> httpx.Response:
    """Simulate PayPal rejecting the client credentials."""
    return httpx.Response(
        401,
        json={"error": "invalid_client", "error_description": "Client Authentication failed"},
    )
