"""Payment links and QR codes for sent invoices.

The only link CollectIQ ever shares is PayPal's own hosted page for that exact
invoice: it must be https, on a PayPal host, and contain the invoice ID.
"""

from urllib.parse import urlparse

import segno

from app.core.exceptions import ConflictError
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.schemas.payment_links import PaymentLinkResponse
from app.services.client_insights import client_key
from app.services.invoice_analysis import COLLECTIBLE_STATUSES, collectible_amount
from app.services.invoices import to_invoice_summary

PAYPAL_HOSTS = frozenset({"www.sandbox.paypal.com", "sandbox.paypal.com"})  # Sandbox only.
QR_DARK = "#0E2233"


def compact_invoice_id(invoice_id: str) -> str:
    """PayPal's payment page uses the ID without the INV2- prefix and dashes (#3U7HDN6DQQQXXGHT)."""
    return invoice_id.removeprefix("INV2-").replace("-", "")


def is_paypal_invoice_url(url: str | None, invoice_id: str) -> bool:
    """True only for PayPal's https invoice page of this exact invoice."""
    if not url:
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in PAYPAL_HOSTS
        and parsed.username is None
        and parsed.port is None
        and "/invoice/" in parsed.path
        and (parsed.fragment == compact_invoice_id(invoice_id) or invoice_id in url)
    )


def qr_svg_data_uri(url: str) -> str:
    return segno.make(url, error="m").svg_data_uri(scale=6, border=2, dark=QR_DARK, light="#FFFFFF")


async def get_payment_link(api: PayPalInvoicesAPI, invoice_id: str) -> PaymentLinkResponse:
    invoice = await api.get_invoice(invoice_id)  # PayPal is the source of truth.
    summary = to_invoice_summary(invoice)
    if summary.status.upper() not in COLLECTIBLE_STATUSES:
        raise ConflictError(f"Only sent, unpaid invoices have a payment link (PayPal status {summary.status}).")

    url = invoice.detail.metadata.recipient_view_url if invoice.detail and invoice.detail.metadata else None
    if not is_paypal_invoice_url(url, invoice_id):
        raise ConflictError("PayPal did not return a valid payment page for this invoice.")
    assert url is not None

    return PaymentLinkResponse(
        invoice_id=invoice_id,
        invoice_number=summary.invoice_number,
        client=client_key(summary),
        status=summary.status,
        amount_due=collectible_amount(summary),
        currency_code=summary.currency_code,
        pay_url=url,
        qr_svg_data_uri=qr_svg_data_uri(url),
    )
