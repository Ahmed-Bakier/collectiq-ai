"""Invoice service: maps PayPal data to CollectIQ's invoice models."""

from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.integrations.paypal.schemas import PayPalBillingInfo, PayPalInvoice
from app.schemas.invoices import InvoiceListResponse, InvoiceSummary


def _recipient_name(billing: PayPalBillingInfo | None) -> str | None:
    if billing is None:
        return None
    if billing.name is not None:
        if billing.name.full_name:
            return billing.name.full_name
        parts = [part for part in (billing.name.given_name, billing.name.surname) if part]
        if parts:
            return " ".join(parts)
    return billing.business_name


def to_invoice_summary(invoice: PayPalInvoice) -> InvoiceSummary:
    """Convert a raw PayPal invoice into the normalized summary model."""
    detail = invoice.detail
    payment_term = detail.payment_term if detail else None
    billing = invoice.primary_recipients[0].billing_info if invoice.primary_recipients else None

    currency_code = detail.currency_code if detail else None
    if currency_code is None and invoice.amount is not None:
        currency_code = invoice.amount.currency_code

    return InvoiceSummary(
        id=invoice.id,
        invoice_number=detail.invoice_number if detail else None,
        status=invoice.status,
        recipient_name=_recipient_name(billing),
        recipient_email=billing.email_address if billing else None,
        currency_code=currency_code,
        total_amount=invoice.amount.value if invoice.amount else None,
        amount_due=invoice.due_amount.value if invoice.due_amount else None,
        invoice_date=detail.invoice_date if detail else None,
        due_date=payment_term.due_date if payment_term else None,
        payment_term=payment_term.term_type if payment_term else None,
    )


class InvoiceService:
    """Read-only invoice operations. PayPal remains the source of truth."""

    def __init__(self, invoices_api: PayPalInvoicesAPI) -> None:
        self._api = invoices_api

    async def list_invoices(self, page: int, page_size: int) -> InvoiceListResponse:
        result = await self._api.list_invoices(page=page, page_size=page_size)
        return InvoiceListResponse(
            items=[to_invoice_summary(invoice) for invoice in result.items],
            page=page,
            page_size=page_size,
            total_items=result.total_items,
            total_pages=result.total_pages,
            source=f"paypal_{self._api.environment}",
        )
