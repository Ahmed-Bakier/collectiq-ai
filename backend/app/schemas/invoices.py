"""Public invoice API models used by the CollectIQ frontend."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class InvoiceSummary(BaseModel):
    """Normalized invoice data. Values come from PayPal; None means unknown."""

    id: str
    invoice_number: str | None = None
    status: str
    recipient_name: str | None = None
    recipient_business_name: str | None = None
    recipient_email: str | None = None
    currency_code: str | None = None
    total_amount: Decimal | None = None
    amount_due: Decimal | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    payment_term: str | None = None


class InvoiceListResponse(BaseModel):
    items: list[InvoiceSummary]
    page: int
    page_size: int
    total_items: int | None = None
    total_pages: int | None = None
    source: str  # e.g. "paypal_sandbox"
