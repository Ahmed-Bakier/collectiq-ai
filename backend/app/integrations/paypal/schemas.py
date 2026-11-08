"""Pydantic models for raw PayPal Invoicing v2 responses.

All fields except `id` and `status` are optional: missing data stays None
and is never guessed.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PayPalModel(BaseModel):
    """Base model that ignores unknown PayPal fields."""

    model_config = ConfigDict(extra="ignore")


class PayPalMoney(PayPalModel):
    currency_code: str
    value: Decimal


class PayPalName(PayPalModel):
    given_name: str | None = None
    surname: str | None = None
    full_name: str | None = None


class PayPalBillingInfo(PayPalModel):
    name: PayPalName | None = None
    business_name: str | None = None
    email_address: str | None = None


class PayPalRecipient(PayPalModel):
    billing_info: PayPalBillingInfo | None = None


class PayPalPaymentTerm(PayPalModel):
    term_type: str | None = None
    due_date: date | None = None


class PayPalInvoiceMetadata(PayPalModel):
    create_time: datetime | None = None
    last_update_time: datetime | None = None
    first_sent_time: datetime | None = None
    last_sent_time: datetime | None = None
    recipient_view_url: str | None = None  # PayPal-hosted page where the client views and pays.


class PayPalInvoiceDetail(PayPalModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency_code: str | None = None
    payment_term: PayPalPaymentTerm | None = None
    metadata: PayPalInvoiceMetadata | None = None


class PayPalPaymentTransaction(PayPalModel):
    """One payment recorded on an invoice (PayPal or external, e.g. bank transfer)."""

    payment_id: str | None = None
    payment_date: str | None = None  # "YYYY-MM-DD", parsed leniently by the services.
    method: str | None = None
    type: str | None = None
    amount: PayPalMoney | None = None


class PayPalPayments(PayPalModel):
    paid_amount: PayPalMoney | None = None
    transactions: list[PayPalPaymentTransaction] = []


class PayPalInvoice(PayPalModel):
    id: str
    status: str
    detail: PayPalInvoiceDetail | None = None
    primary_recipients: list[PayPalRecipient] = []
    amount: PayPalMoney | None = None
    due_amount: PayPalMoney | None = None
    payments: PayPalPayments | None = None


class PayPalInvoiceList(PayPalModel):
    items: list[PayPalInvoice] = []
    total_items: int | None = None
    total_pages: int | None = None
