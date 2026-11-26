"""Payment link and QR code API models."""

from decimal import Decimal

from pydantic import BaseModel


class PaymentLinkResponse(BaseModel):
    invoice_id: str
    invoice_number: str | None = None
    client: str
    status: str
    amount_due: Decimal | None = None
    currency_code: str | None = None
    pay_url: str  # PayPal-hosted invoice page (validated).
    qr_svg_data_uri: str  # QR code of pay_url, as a data: URI for an <img>.
