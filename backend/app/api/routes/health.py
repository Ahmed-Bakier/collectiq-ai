"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Public health status. Must never include secrets."""

    status: str
    app: str
    environment: str
    paypal_environment: str
    paypal_credentials_configured: bool


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Report basic service health and safe configuration state."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.app_env,
        paypal_environment=settings.paypal_environment,
        paypal_credentials_configured=settings.paypal_credentials_configured,
    )
