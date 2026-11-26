"""Client payment intelligence and collections forecast (read-only)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_invoice_service, get_today
from app.core.config import get_settings
from app.schemas.insights import InsightsResponse
from app.services.client_insights import ClientInsightsService
from app.services.invoices import InvoiceService

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("", response_model=InsightsResponse)
async def get_insights(
    service: Annotated[InvoiceService, Depends(get_invoice_service)],
    today: Annotated[date, Depends(get_today)],
) -> InsightsResponse:
    """Per-client payment behaviour and a 30-day expected-collections forecast."""
    return await ClientInsightsService(service).build(today, get_settings().business_timezone)
