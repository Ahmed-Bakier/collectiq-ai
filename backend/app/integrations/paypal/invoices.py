"""PayPal Invoicing v2 adapter (read operations)."""

from pydantic import ValidationError

from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.exceptions import PayPalAPIError
from app.integrations.paypal.schemas import PayPalInvoiceList

INVOICES_PATH = "/v2/invoicing/invoices"
MAX_PAGE_SIZE = 100  # Documented PayPal limit.


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
