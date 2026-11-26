"""Integration status endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.integrations.paypal.auth import PayPalTokenProvider
from app.integrations.paypal.dependencies import get_token_provider
from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalAuthError,
    PayPalConfigurationError,
    PayPalConnectionError,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


class PayPalStatusResponse(BaseModel):
    """Safe-to-display PayPal connection state. Never contains tokens or secrets."""

    environment: str
    credentials_configured: bool
    connected: bool
    app_id: str | None = None
    checked_at: datetime
    error: str | None = None


@router.get("/paypal/status", response_model=PayPalStatusResponse)
async def paypal_status(
    token_provider: Annotated[PayPalTokenProvider, Depends(get_token_provider)],
) -> PayPalStatusResponse:
    """Check PayPal connectivity by obtaining an access token."""
    settings = token_provider.settings
    checked_at = datetime.now(timezone.utc)
    error: str

    try:
        token = await token_provider.get_token()
    except PayPalConfigurationError:
        error = "PayPal credentials are not configured on the server."
    except PayPalAuthError:
        error = "PayPal rejected the configured credentials."
    except PayPalConnectionError:
        error = "Could not reach PayPal. Check the network connection."
    except PayPalAPIError as exc:
        error = f"PayPal returned an unexpected error (HTTP {exc.status_code})."
    else:
        return PayPalStatusResponse(
            environment=settings.paypal_environment,
            credentials_configured=True,
            connected=True,
            app_id=token.app_id,
            checked_at=checked_at,
        )

    return PayPalStatusResponse(
        environment=settings.paypal_environment,
        credentials_configured=settings.paypal_credentials_configured,
        connected=False,
        checked_at=checked_at,
        error=error,
    )
