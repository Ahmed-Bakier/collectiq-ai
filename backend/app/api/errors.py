"""Consistent, safe error responses for the API."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalAuthError,
    PayPalConfigurationError,
    PayPalConnectionError,
    PayPalError,
)

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    paypal_debug_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "paypal_debug_id": paypal_debug_id}},
    )


async def handle_paypal_error(request: Request, exc: Exception) -> JSONResponse:
    """Map PayPal integration errors to safe HTTP responses (no stack traces, no secrets)."""
    logger.warning("PayPal error on %s %s: %s", request.method, request.url.path, type(exc).__name__)

    if isinstance(exc, PayPalConfigurationError):
        return _error_response(503, "paypal_not_configured", "PayPal credentials are not configured on the server.")
    if isinstance(exc, PayPalAuthError):
        return _error_response(502, "paypal_auth_failed", "PayPal rejected the configured credentials.")
    if isinstance(exc, PayPalConnectionError):
        return _error_response(504, "paypal_unreachable", "PayPal did not respond. Please try again.")
    if isinstance(exc, PayPalAPIError):
        return _error_response(
            502,
            "paypal_api_error",
            f"PayPal returned an error (HTTP {exc.status_code}).",
            exc.debug_id,
        )
    return _error_response(502, "paypal_error", "Unexpected PayPal integration error.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PayPalError, handle_paypal_error)
