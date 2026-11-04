"""Shared FastAPI dependencies for API routes."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends

from app.core.config import get_settings
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.dependencies import get_paypal_client
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.services.invoices import InvoiceService


def get_invoice_service(
    client: Annotated[PayPalClient, Depends(get_paypal_client)],
) -> InvoiceService:
    return InvoiceService(PayPalInvoicesAPI(client))


def get_today() -> date:
    """Today's date in the configured business timezone (overridden in tests)."""
    return datetime.now(ZoneInfo(get_settings().business_timezone)).date()
