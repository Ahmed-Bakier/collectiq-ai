"""Tests for GET /api/invoices (mocked HTTP)."""

import httpx
from fastapi.testclient import TestClient

from app.integrations.paypal.auth import PayPalTokenProvider
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from tests.fakes import make_paypal_client, make_settings, sample_paypal_invoice


def get_with_client(client: PayPalClient, url: str) -> httpx.Response:
    app.dependency_overrides[get_paypal_client] = lambda: client
    try:
        return TestClient(app).get(url)
    finally:
        app.dependency_overrides.clear()


def test_list_invoices_route_returns_normalized_invoices() -> None:
    client = make_paypal_client(
        lambda request: httpx.Response(
            200,
            json={"items": [sample_paypal_invoice()], "total_items": 1, "total_pages": 1},
        )
    )
    response = get_with_client(client, "/api/invoices")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "paypal_sandbox"
    assert body["items"][0]["id"] == "INV2-TEST-AAAA-BBBB-CCCC"
    assert body["items"][0]["total_amount"] == "250.00"  # Money is serialized as a string.


def test_page_size_above_limit_is_rejected() -> None:
    client = make_paypal_client(lambda request: httpx.Response(200, json={}))
    response = get_with_client(client, "/api/invoices?page_size=500")
    assert response.status_code == 422


def test_paypal_failure_returns_safe_error() -> None:
    client = make_paypal_client(
        lambda request: httpx.Response(
            500,
            json={"name": "INTERNAL_SERVER_ERROR"},
            headers={"paypal-debug-id": "dbg-123"},
        )
    )
    response = get_with_client(client, "/api/invoices")

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "paypal_api_error"
    assert error["paypal_debug_id"] == "dbg-123"
    assert "Traceback" not in response.text


def test_missing_credentials_returns_503() -> None:
    provider = PayPalTokenProvider(make_settings(paypal_client_id="", paypal_client_secret=""))
    response = get_with_client(PayPalClient(provider), "/api/invoices")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "paypal_not_configured"
