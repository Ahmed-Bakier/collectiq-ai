"""Invoice endpoints. PayPal is the source of truth for all invoice data."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_invoice_service, get_today
from app.core.config import get_settings
from app.schemas.analysis import InvoiceAnalysisResponse
from app.schemas.invoices import InvoiceListResponse
from app.services.invoice_analysis import analyze_invoices
from app.services.invoices import InvoiceService

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    service: Annotated[InvoiceService, Depends(get_invoice_service)],
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> InvoiceListResponse:
    """List invoices from PayPal, normalized for the CollectIQ UI."""
    return await service.list_invoices(page=page, page_size=page_size)


@router.get("/analysis", response_model=InvoiceAnalysisResponse)
async def analyze_all_invoices(
    service: Annotated[InvoiceService, Depends(get_invoice_service)],
    today: Annotated[date, Depends(get_today)],
) -> InvoiceAnalysisResponse:
    """Deterministic collection analysis of all PayPal invoices."""
    invoices = await service.list_all_invoices()
    return analyze_invoices(invoices, today=today, timezone=get_settings().business_timezone)
