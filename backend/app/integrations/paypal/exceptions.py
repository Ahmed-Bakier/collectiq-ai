"""Typed exceptions for the PayPal integration layer."""


class PayPalError(Exception):
    """Base exception for all PayPal integration errors."""


class PayPalConfigurationError(PayPalError):
    """Raised when PayPal credentials are missing or still placeholders."""


class PayPalAuthError(PayPalError):
    """Raised when PayPal rejects the configured client credentials."""


class PayPalConnectionError(PayPalError):
    """Raised on network failures or timeouts while calling PayPal."""


class PayPalAPIError(PayPalError):
    """Raised when PayPal returns an unexpected or error response."""

    def __init__(self, status_code: int, message: str, debug_id: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.debug_id = debug_id
