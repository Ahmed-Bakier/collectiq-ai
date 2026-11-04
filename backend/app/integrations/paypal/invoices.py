"""PayPal Invoicing v2 adapter."""

import re
from typing import Any

from pydantic import ValidationError

from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.exceptions import PayPalAPIError
from app.integrations.paypal.schemas import PayPalInvoice, PayPalInvoiceList

INVOICES_PATH = "/v2/invoicing/invoices"
MAX_PAGE_SIZE = 100  # Documented PayPal limit.

# PayPal invoice IDs look like INV2-XXXX-XXXX-XXXX-XXXX (max 30 chars per docs).
# Strict validation also prevents path injection into PayPal URLs.
INVOICE_ID_PATTERN = re.compile(r"^[A-Z0-9-]{1,30}$")


def validate_invoice_id(invoice_id: str) -> str:
    if not INVOICE_ID_PATTERN.fullmatch(invoice_id):
        raise ValueError("Invalid PayPal invoice ID.")
    return invoice_id


def _extract_invoice_id(payload: dict[str, Any]) -> str | None:
    """Read the invoice ID from either a full representation or a HATEOAS link."""
    candidate = payload.get("id")
    if candidate is None:
        href = payload.get("href")
        if isinstance(href, str):
            candidate = href.rstrip("/").rsplit("/", 1)[-1]
    if isinstance(candidate, str) and INVOICE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return None


class PayPalInvoicesAPI:
    """Typed wrapper around the PayPal invoice endpoints."""

    def __init__(self, client: PayPalClient) -> None:
        self._client = client

    @property
    def environment(self) -> str:
        return self._client.settings.paypal_environment

    async def list_invoices(self, page: int = 1, page_size: int = 20) -> PayPalInvoiceList:
        """List invoices for the authenticated merchant."""
        if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError("Invalid pagination parameters.")

        payload = await self._client.get(
            INVOICES_PATH,
            params={"page": page, "page_size": page_size, "total_required": "true"},
        )
        try:
            return PayPalInvoiceList.model_validate(payload)
        except ValidationError as exc:
            raise PayPalAPIError(200, "Unexpected invoice list format from PayPal.") from exc

    async def get_invoice(self, invoice_id: str) -> PayPalInvoice:
        """Read a single invoice. Used to verify the result of write operations."""
        payload = await self._client.get(f"{INVOICES_PATH}/{validate_invoice_id(invoice_id)}")
        try:
            return PayPalInvoice.model_validate(payload)
        except ValidationError as exc:
            raise PayPalAPIError(200, "Unexpected invoice format from PayPal.") from exc

    async def create_draft_invoice(self, invoice: dict[str, Any], request_id: str) -> str:
        """Create a draft invoice and return its PayPal ID. External write operation."""
        payload = await self._client.post(INVOICES_PATH, invoice, request_id)
        invoice_id = _extract_invoice_id(payload)
        if invoice_id is None:
            raise PayPalAPIError(201, "PayPal did not return the created invoice ID.")
        return invoice_id

    async def send_invoice(
        self,
        invoice_id: str,
        request_id: str,
        *,
        send_to_recipient: bool = True,
        send_to_invoicer: bool = False,
    ) -> None:
        """Send a draft invoice to its recipient. External write operation."""
        await self._client.post(
            f"{INVOICES_PATH}/{validate_invoice_id(invoice_id)}/send",
            {"send_to_recipient": send_to_recipient, "send_to_invoicer": send_to_invoicer},
            request_id,
        )
