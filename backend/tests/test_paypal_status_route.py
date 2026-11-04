"""Tests for GET /api/integrations/paypal/status (mocked HTTP)."""

import httpx
from fastapi.testclient import TestClient

from app.integrations.paypal.auth import PayPalTokenProvider
from app.integrations.paypal.dependencies import get_token_provider
from app.main import app
from tests.fakes import (
    FAKE_ACCESS_TOKEN,
    FAKE_APP_ID,
    make_settings,
    token_ok_handler,
    token_rejected_handler,
)


def call_status_with(provider: PayPalTokenProvider) -> dict:
    app.dependency_overrides[get_token_provider] = lambda: provider
    try:
        response = TestClient(app).get("/api/integrations/paypal/status")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.json()


def test_status_connected_without_leaking_token() -> None:
    provider = PayPalTokenProvider(make_settings(), transport=httpx.MockTransport(token_ok_handler))
    body = call_status_with(provider)

    assert body["connected"] is True
    assert body["credentials_configured"] is True
    assert body["environment"] == "sandbox"
    assert body["app_id"] == FAKE_APP_ID
    assert body["error"] is None
    assert FAKE_ACCESS_TOKEN not in str(body)


def test_status_reports_rejected_credentials() -> None:
    provider = PayPalTokenProvider(
        make_settings(), transport=httpx.MockTransport(token_rejected_handler)
    )
    body = call_status_with(provider)

    assert body["connected"] is False
    assert body["error"] == "PayPal rejected the configured credentials."


def test_status_reports_missing_credentials() -> None:
    provider = PayPalTokenProvider(make_settings(paypal_client_id="", paypal_client_secret=""))
    body = call_status_with(provider)

    assert body["connected"] is False
    assert body["credentials_configured"] is False
