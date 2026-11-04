"""Seed the PayPal Sandbox with CollectIQ demo invoices.

Safety rules:
- Sandbox only: refuses to run against any non-sandbox PayPal URL.
- Dry-run by default: prints the plan and makes NO PayPal calls.
- Writes only with --execute AND an interactive "yes" confirmation.
- Every write uses a unique PayPal-Request-Id; failed writes are never retried.

Usage (from backend/):
    python scripts/seed_sandbox_invoices.py            # dry-run
    python scripts/seed_sandbox_invoices.py --execute  # create + send (asks to confirm)
"""

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings  # noqa: E402
from app.integrations.paypal.auth import PayPalTokenProvider  # noqa: E402
from app.integrations.paypal.client import PayPalClient  # noqa: E402
from app.integrations.paypal.exceptions import PayPalAPIError, PayPalError  # noqa: E402
from app.integrations.paypal.invoices import PayPalInvoicesAPI  # noqa: E402

# PayPal sends immediately only when the invoice date is today or earlier.
# Using the US Pacific date avoids a "future" date for the US sandbox merchant.
MERCHANT_TIMEZONE = ZoneInfo("America/Los_Angeles")
CURRENCY = "USD"
INVOICE_NUMBER_MAX_LENGTH = 25  # Documented PayPal limit.


@dataclass(frozen=True)
class SeedInvoice:
    client_name: str
    contact_given_name: str
    contact_surname: str
    contact_email: str  # Must use the reserved example.com domain.
    description: str
    amount: Decimal
    due_in_days: int
    send: bool


SEED_INVOICES: tuple[SeedInvoice, ...] = (
    SeedInvoice("Acme Design Studio", "Olivia", "Grant", "billing.acme@example.com",
                "Brand identity package", Decimal("1200.00"), 1, True),
    SeedInvoice("Northwind Traders", "Liam", "Carter", "ap.northwind@example.com",
                "Website maintenance - October", Decimal("450.00"), 2, True),
    SeedInvoice("Blue Harbor Cafe", "Emma", "Lopez", "owner.blueharbor@example.com",
                "Menu and social media design", Decimal("780.00"), 5, True),
    SeedInvoice("Lumen Analytics", "Noah", "Patel", "finance.lumen@example.com",
                "Dashboard UX audit", Decimal("2350.00"), 14, True),
    SeedInvoice("Pixel & Co", "Ava", "Kim", "hello.pixelco@example.com",
                "Landing page copywriting", Decimal("300.00"), 7, False),
)


def merchant_today() -> date:
    return datetime.now(MERCHANT_TIMEZONE).date()


def build_invoice_number(batch_stamp: str, index: int) -> str:
    """Return a unique invoice number, e.g. CIQ-2611040830-01."""
    number = f"CIQ-{batch_stamp}-{index:02d}"
    if len(number) > INVOICE_NUMBER_MAX_LENGTH:
        raise ValueError("Invoice number exceeds the PayPal length limit.")
    return number


def build_invoice_payload(
    seed: SeedInvoice,
    invoice_number: str,
    invoice_date: date,
    invoicer_email: str,
) -> dict[str, Any]:
    """Build a PayPal Invoicing v2 create-draft request body."""
    due_date = invoice_date + timedelta(days=seed.due_in_days)
    return {
        "detail": {
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.isoformat(),
            "currency_code": CURRENCY,
            "note": "Thank you for your business.",
            "memo": "CollectIQ AI demo data (PayPal Sandbox).",
            "payment_term": {
                "term_type": "DUE_ON_DATE_SPECIFIED",
                "due_date": due_date.isoformat(),
            },
        },
        "invoicer": {
            "business_name": "CollectIQ Demo Studio",
            "email_address": invoicer_email,
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {
                        "given_name": seed.contact_given_name,
                        "surname": seed.contact_surname,
                    },
                    "business_name": seed.client_name,
                    "email_address": seed.contact_email,
                }
            }
        ],
        "items": [
            {
                "name": seed.description,
                "quantity": "1",
                "unit_amount": {"currency_code": CURRENCY, "value": f"{seed.amount:.2f}"},
            }
        ],
    }


def print_plan(settings: Settings, invoice_date: date, batch_stamp: str) -> None:
    print("CollectIQ AI - PayPal Sandbox seed plan")
    print(f"PayPal URL:   {settings.paypal_base_url}")
    print(f"Invoicer:     {settings.paypal_sandbox_invoicer_email}")
    print(f"Invoice date: {invoice_date.isoformat()} ({MERCHANT_TIMEZONE.key})\n")
    print(f"{'#':<3}{'Number':<20}{'Client':<22}{'Amount':>12}  {'Due date':<12}Action")
    for index, seed in enumerate(SEED_INVOICES, start=1):
        due_date = invoice_date + timedelta(days=seed.due_in_days)
        action = "create + send" if seed.send else "create draft only"
        print(
            f"{index:<3}{build_invoice_number(batch_stamp, index):<20}{seed.client_name:<22}"
            f"{seed.amount:>8} {CURRENCY}  {due_date.isoformat():<12}{action}"
        )


async def execute(settings: Settings, invoice_date: date, batch_stamp: str) -> int:
    api = PayPalInvoicesAPI(PayPalClient(PayPalTokenProvider(settings)))
    invoicer_email = settings.paypal_sandbox_invoicer_email or ""

    for index, seed in enumerate(SEED_INVOICES, start=1):
        number = build_invoice_number(batch_stamp, index)
        payload = build_invoice_payload(seed, number, invoice_date, invoicer_email)
        try:
            invoice_id = await api.create_draft_invoice(payload, request_id=str(uuid.uuid4()))
            print(f"[created]  {number} -> {invoice_id}")

            if seed.send:
                await api.send_invoice(invoice_id, request_id=str(uuid.uuid4()))
                print(f"[sent]     {invoice_id}")

            verified = await api.get_invoice(invoice_id)
            print(f"[verified] {invoice_id} status={verified.status}")
        except PayPalError as exc:
            debug_id = exc.debug_id if isinstance(exc, PayPalAPIError) else None
            print(f"[FAILED]   {number}: {type(exc).__name__}: {exc} (debug_id={debug_id})")
            print("Stopped. Nothing was retried. Check the Sandbox dashboard before re-running.")
            return 1

    print("\nDone. All seed invoices were created and verified.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PayPal Sandbox with demo invoices.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create and send invoices in PayPal Sandbox.",
    )
    args = parser.parse_args()
    settings = get_settings()

    if settings.paypal_environment != "sandbox" or "sandbox" not in settings.paypal_base_url:
        print("Refusing to run: this script is for PayPal Sandbox only.")
        return 1
    if not settings.paypal_credentials_configured:
        print("PayPal credentials are not configured in backend/.env")
        return 1
    if not settings.paypal_sandbox_invoicer_email:
        print("Set PAYPAL_SANDBOX_INVOICER_EMAIL in backend/.env")
        return 1

    invoice_date = merchant_today()
    batch_stamp = datetime.now(MERCHANT_TIMEZONE).strftime("%y%m%d%H%M")
    print_plan(settings, invoice_date, batch_stamp)

    if not args.execute:
        print("\nDRY RUN: no PayPal calls were made. Re-run with --execute to create these invoices.")
        return 0

    total = len(SEED_INVOICES)
    to_send = sum(1 for seed in SEED_INVOICES if seed.send)
    answer = input(
        f"\nThis will CREATE {total} invoices and SEND {to_send} of them in PayPal Sandbox.\n"
        "Type 'yes' to continue: "
    )
    if answer.strip().lower() != "yes":
        print("Cancelled. Nothing was created.")
        return 0

    return asyncio.run(execute(settings, invoice_date, batch_stamp))


if __name__ == "__main__":
    sys.exit(main())
