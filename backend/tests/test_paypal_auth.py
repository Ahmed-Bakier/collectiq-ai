"""Unit tests for PayPalTokenProvider (mocked HTTP)."""

import asyncio

import httpx
import pytest

from app.integrations.paypal.auth import TOKEN_PATH, PayPalTokenProvider
from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalAuthError,
    PayPalConfigurationError,
)
from tests.fakes import (
    FAKE_ACCESS_TOKEN,
    FAKE_APP_ID,
    make_settings,
    token_ok_handler,
    token_rejected_handler,
)


def test_get_token_sends_correct_request_and_caches_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return token_ok_handler(request)

    provider = PayPalTokenProvider(make_settings(), transport=httpx.MockTransport(handler))

    async def run() -> tuple:
        return await provider.get_token(), await provider.get_token()

    first, second = asyncio.run(run())

    assert first.value == FAKE_ACCESS_TOKEN
    assert first.app_id == FAKE_APP_ID
    assert second is first  # Second call must reuse the cached token.
    assert len(requests) == 1

    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == TOKEN_PATH
    assert request.headers["Authorization"].startswith("Basic ")
    assert b"grant_type=client_credentials" in request.content


def test_force_refresh_requests_new_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return token_ok_handler(request)

    provider = PayPalTokenProvider(make_settings(), transport=httpx.MockTransport(handler))

    async def run() -> None:
        await provider.get_token()
        await provider.get_token(force_refresh=True)

    asyncio.run(run())
    assert len(requests) == 2


def test_rejected_credentials_raise_auth_error() -> None:
    provider = PayPalTokenProvider(
        make_settings(), transport=httpx.MockTransport(token_rejected_handler)
    )
    with pytest.raises(PayPalAuthError):
        asyncio.run(provider.get_token())


def test_placeholder_credentials_never_call_paypal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("PayPal must not be called without real credentials")

    provider = PayPalTokenProvider(
        make_settings(paypal_client_id="your-sandbox-client-id"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(PayPalConfigurationError):
        asyncio.run(provider.get_token())


def test_malformed_token_response_raises_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})

    provider = PayPalTokenProvider(make_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(PayPalAPIError):
        asyncio.run(provider.get_token())


def test_network_timeout_raises_connection_error() -> None:
    from app.integrations.paypal.exceptions import PayPalConnectionError

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout", request=request)

    provider = PayPalTokenProvider(make_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(PayPalConnectionError):
        asyncio.run(provider.get_token())
