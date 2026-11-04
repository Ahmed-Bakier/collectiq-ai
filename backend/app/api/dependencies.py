"""Shared FastAPI dependencies for API routes."""

from typing import Annotated

from fastapi import Depends

from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.dependencies import get_paypal_client
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.services.invoices import InvoiceService


def get_invoice_service(
    client: Annotated[PayPalClient, Depends(get_paypal_client)],
) -> InvoiceService:
    return InvoiceService(PayPalInvoicesAPI(client))
