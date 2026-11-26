"""FastAPI dependencies for the PayPal integration."""

from functools import lru_cache

from app.core.config import get_settings
from app.integrations.paypal.auth import PayPalTokenProvider
from app.integrations.paypal.client import PayPalClient


@lru_cache
def get_token_provider() -> PayPalTokenProvider:
    """Return a process-wide token provider so the access token is cached and reused."""
    return PayPalTokenProvider(get_settings())


@lru_cache
def get_paypal_client() -> PayPalClient:
    """Return a process-wide PayPal client sharing the cached token provider."""
    return PayPalClient(get_token_provider())
