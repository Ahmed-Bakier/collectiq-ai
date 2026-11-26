"""Shared test helpers. These fakes never contact the real PayPal API."""

from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.paypal.auth import TOKEN_PATH, PayPalTokenProvider
from app.integrations.paypal.client import PayPalClient

FAKE_ACCESS_TOKEN = "fake-access-token"
FAKE_APP_ID = "APP-TEST-123"

ApiHandler = Callable[[httpx.Request], httpx.Response]


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


def make_paypal_transport(
    api_handler: ApiHandler,
    token_requests: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """Route token requests to a fake token endpoint and all other calls to api_handler."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            if token_requests is not None:
                token_requests.append(request)
            return token_ok_handler(request)
        return api_handler(request)

    return httpx.MockTransport(handler)


def make_paypal_client(
    api_handler: ApiHandler,
    token_requests: list[httpx.Request] | None = None,
) -> PayPalClient:
    transport = make_paypal_transport(api_handler, token_requests)
    provider = PayPalTokenProvider(make_settings(), transport=transport)
    return PayPalClient(provider, transport=transport)


def sample_paypal_invoice(**overrides: Any) -> dict[str, Any]:
    """A realistic PayPal invoice payload (fake data)."""
    invoice: dict[str, Any] = {
        "id": "INV2-TEST-AAAA-BBBB-CCCC",
        "status": "UNPAID",
        "detail": {
            "invoice_number": "CIQ-TEST-001",
            "invoice_date": "2026-11-01",
            "currency_code": "USD",
            "payment_term": {"term_type": "DUE_ON_DATE_SPECIFIED", "due_date": "2026-11-15"},
            "metadata": {"create_time": "2026-11-01T10:00:00Z"},
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": "Jane", "surname": "Doe"},
                    "email_address": "jane@example.com",
                }
            }
        ],
        "amount": {"currency_code": "USD", "value": "250.00"},
        "due_amount": {"currency_code": "USD", "value": "250.00"},
    }
    invoice.update(overrides)
    return invoice
