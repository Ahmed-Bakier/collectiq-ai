"""Authenticated HTTP client for the PayPal REST API."""

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.paypal.auth import REQUEST_TIMEOUT_SECONDS, PayPalTokenProvider
from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalConnectionError,
    PayPalWriteOutcomeUnknownError,
)

logger = logging.getLogger(__name__)


class PayPalClient:
    """Sends authenticated requests to PayPal."""

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
        response = await self._send("GET", path, token.value, params=params)

        if response.status_code == 401:
            # The token may have expired early or been revoked: refresh once and retry.
            # Safe for GET requests because they have no side effects.
            token = await self._token_provider.get_token(force_refresh=True)
            response = await self._send("GET", path, token.value, params=params)

        return _parse_response(response)

    async def post(self, path: str, json_body: dict[str, Any], request_id: str) -> dict[str, Any]:
        """Send an authenticated write request.

        `request_id` is sent as PayPal-Request-Id so PayPal can de-duplicate the request.
        Network failures after sending raise PayPalWriteOutcomeUnknownError and are
        never retried here.
        """
        if not request_id:
            raise ValueError("A PayPal-Request-Id is required for write operations.")

        extra_headers = {"PayPal-Request-Id": request_id, "Content-Type": "application/json"}
        token = await self._token_provider.get_token()
        response = await self._send(
            "POST", path, token.value, json_body=json_body, extra_headers=extra_headers
        )

        if response.status_code == 401:
            # A 401 means PayPal rejected the token before processing the request,
            # so one retry with a fresh token and the SAME request ID is safe.
            token = await self._token_provider.get_token(force_refresh=True)
            response = await self._send(
                "POST", path, token.value, json_body=json_body, extra_headers=extra_headers
            )

        return _parse_response(response)

    async def _send(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            **(extra_headers or {}),
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.paypal_base_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                return await client.request(
                    method, path, params=params, json=json_body, headers=headers
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # The connection was never established, so the request was not sent.
            raise PayPalConnectionError(f"Could not connect to PayPal ({method} {path}).") from exc
        except httpx.HTTPError as exc:
            if method != "GET":
                raise PayPalWriteOutcomeUnknownError(
                    f"Outcome unknown for PayPal {method} {path}: "
                    "the request may or may not have been applied."
                ) from exc
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
    """Build a human-readable message from a PayPal error body (for server logs)."""
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

    details = payload.get("details")
    if isinstance(details, list) and details and isinstance(details[0], dict):
        first = details[0]
        extra = " ".join(
            str(value) for value in (first.get("field"), first.get("issue"), first.get("description")) if value
        )
        if extra:
            parts.append(f"({extra})")

    return ": ".join(parts) if parts else fallback
