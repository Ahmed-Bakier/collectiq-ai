"""OAuth 2.0 client-credentials token provider for the PayPal REST API."""

import asyncio
import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalAuthError,
    PayPalConfigurationError,
    PayPalConnectionError,
)

TOKEN_PATH = "/v1/oauth2/token"
REQUEST_TIMEOUT_SECONDS = 15.0
# Refresh the token slightly before it actually expires.
EXPIRY_SAFETY_MARGIN_SECONDS = 60


@dataclass(frozen=True)
class AccessToken:
    """A PayPal access token. Never log or return `value` to clients."""

    value: str
    expires_at: float  # time.monotonic() based
    app_id: str | None = None

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at - EXPIRY_SAFETY_MARGIN_SECONDS


class PayPalTokenProvider:
    """Requests and caches PayPal access tokens."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport  # Injected in tests to mock HTTP calls.
        self._token: AccessToken | None = None
        self._lock = asyncio.Lock()

    @property
    def settings(self) -> Settings:
        return self._settings

    async def get_token(self, force_refresh: bool = False) -> AccessToken:
        """Return a valid cached token, or request a new one."""
        async with self._lock:
            if not force_refresh and self._token is not None and self._token.is_valid():
                return self._token
            self._token = await self._request_token()
            return self._token

    def invalidate(self) -> None:
        """Drop the cached token (e.g. after PayPal returns 401)."""
        self._token = None

    async def _request_token(self) -> AccessToken:
        if not self._settings.paypal_credentials_configured:
            raise PayPalConfigurationError("PayPal credentials are not configured.")

        credentials = (
            self._settings.paypal_client_id,
            self._settings.paypal_client_secret.get_secret_value(),
        )

        try:
            async with httpx.AsyncClient(
                base_url=self._settings.paypal_base_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    TOKEN_PATH,
                    data={"grant_type": "client_credentials"},
                    auth=credentials,
                    headers={"Accept": "application/json"},
                )
        except httpx.TimeoutException as exc:
            raise PayPalConnectionError("Timed out while requesting a PayPal access token.") from exc
        except httpx.HTTPError as exc:
            raise PayPalConnectionError("Network error while requesting a PayPal access token.") from exc

        debug_id = response.headers.get("paypal-debug-id")

        if response.status_code == 401:
            raise PayPalAuthError("PayPal rejected the client credentials.")
        if response.status_code != 200:
            raise PayPalAPIError(
                response.status_code,
                "Unexpected response from the PayPal token endpoint.",
                debug_id,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise PayPalAPIError(200, "PayPal token response is not valid JSON.", debug_id) from exc

        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        expires_in = payload.get("expires_in") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token or not isinstance(expires_in, int):
            raise PayPalAPIError(200, "PayPal token response is missing required fields.", debug_id)

        return AccessToken(
            value=access_token,
            expires_at=time.monotonic() + expires_in,
            app_id=payload.get("app_id"),
        )
