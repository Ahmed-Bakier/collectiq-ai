"""Payment link + QR code for one sent invoice (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.dependencies import get_paypal_client
from app.integrations.paypal.invoices import INVOICE_ID_PATTERN, PayPalInvoicesAPI
from app.schemas.payment_links import PaymentLinkResponse
from app.services.payment_links import get_payment_link

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("/{invoice_id}/payment-link", response_model=PaymentLinkResponse)
async def payment_link(
    invoice_id: str,
    client: Annotated[PayPalClient, Depends(get_paypal_client)],
) -> PaymentLinkResponse | JSONResponse:
    """PayPal's hosted payment page for the invoice and a QR code that opens it."""
    if not INVOICE_ID_PATTERN.fullmatch(invoice_id):
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_invoice_id", "message": "Invalid PayPal invoice ID.", "paypal_debug_id": None}},
        )
    return await get_payment_link(PayPalInvoicesAPI(client), invoice_id)
