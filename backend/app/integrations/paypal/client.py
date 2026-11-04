"""Authenticated HTTP client for the PayPal REST API."""

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.paypal.auth import REQUEST_TIMEOUT_SECONDS, PayPalTokenProvider
from app.integrations.paypal.exceptions import PayPalAPIError, PayPalConnectionError

logger = logging.getLogger(__name__)


class PayPalClient:
    """Sends authenticated requests to PayPal.

    Only read (GET) requests are exposed for now. Write operations will be added
    together with idempotency keys (PayPal-Request-Id) and the approval engine.
    """

    def __init__(
        self,
        token_provider: PayPalTokenProvider,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token_provider = token_provider
        self._transport = transport  # Injected in tests to mock HTTP calls.

    @property
    def settings(self) -> Settings:
        return self._token_provider.settings

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send an authenticated GET request and return the JSON body."""
        token = await self._token_provider.get_token()
        response = await self._send("GET", path, token.value, params)

        if response.status_code == 401:
            # The token may have expired early or been revoked: refresh once and retry.
            # Safe for GET requests because they have no side effects.
            token = await self._token_provider.get_token(force_refresh=True)
            response = await self._send("GET", path, token.value, params)

        return _parse_response(response)

    async def _send(
        self,
        method: str,
        path: str,
        access_token: str,
        params: dict[str, Any] | None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.paypal_base_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                return await client.request(method, path, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise PayPalConnectionError(f"Timed out calling PayPal ({method} {path}).") from exc
        except httpx.HTTPError as exc:
            raise PayPalConnectionError(f"Network error calling PayPal ({method} {path}).") from exc


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    """Return the JSON body or raise a typed error. Never exposes tokens."""
    debug_id = response.headers.get("paypal-debug-id")

    if response.status_code >= 400:
        message = _extract_error_message(response)
        logger.warning(
            "PayPal API error: status=%s debug_id=%s message=%s",
            response.status_code,
            debug_id,
            message,
        )
        raise PayPalAPIError(response.status_code, message, debug_id)

    if not response.content:
        return {}

    try:
        payload = response.json()
    except ValueError as exc:
        raise PayPalAPIError(response.status_code, "PayPal response is not valid JSON.", debug_id) from exc

    if not isinstance(payload, dict):
        raise PayPalAPIError(response.status_code, "Unexpected PayPal response format.", debug_id)
    return payload


def _extract_error_message(response: httpx.Response) -> str:
    """Build a safe, human-readable message from a PayPal error body."""
    fallback = f"PayPal returned HTTP {response.status_code}."
    try:
        payload = response.json()
    except ValueError:
        return fallback
    if not isinstance(payload, dict):
        return fallback
    name = payload.get("name") or payload.get("error")
    message = payload.get("message") or payload.get("error_description")
    parts = [str(part) for part in (name, message) if part]
    return ": ".join(parts) if parts else fallback
