"""Consistent, safe error responses for the API."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent.llm import LLMError, LLMNotConfiguredError, LLMRateLimitError
from app.core.exceptions import AppError
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


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _error_response(exc.status_code, exc.code, exc.message)


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


async def handle_llm_error(request: Request, exc: Exception) -> JSONResponse:
    """Map AI provider errors to safe HTTP responses."""
    logger.warning("AI provider error on %s %s: %s", request.method, request.url.path, type(exc).__name__)

    if isinstance(exc, LLMNotConfiguredError):
        return _error_response(503, "ai_not_configured", "The AI provider is not configured on the server.")
    if isinstance(exc, LLMRateLimitError):
        return _error_response(
            429, "ai_rate_limited", "The AI provider rate limit was reached. Please wait a minute and try again."
        )
    return _error_response(502, "ai_error", "The AI provider returned an error.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(PayPalError, handle_paypal_error)
    app.add_exception_handler(LLMError, handle_llm_error)
