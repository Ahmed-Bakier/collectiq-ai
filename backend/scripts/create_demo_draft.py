"""Create ONE draft invoice in PayPal Sandbox for the approval demo.

Dry-run by default; writes only with --execute and an interactive "yes".
Usage (from backend/): python scripts/create_demo_draft.py [--execute]
"""

import argparse
import asyncio
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.integrations.paypal.auth import PayPalTokenProvider  # noqa: E402
from app.integrations.paypal.client import PayPalClient  # noqa: E402
from app.integrations.paypal.exceptions import PayPalError  # noqa: E402
from app.integrations.paypal.invoices import PayPalInvoicesAPI  # noqa: E402
from scripts.seed_sandbox_invoices import (  # noqa: E402
    MERCHANT_TIMEZONE,
    SeedInvoice,
    build_invoice_number,
    build_invoice_payload,
    merchant_today,
)

DEMO_DRAFT = SeedInvoice(
    "Harbor & Pine Studio",
    "Mia",
    "Chen",
    "accounts.harborpine@example.com",
    "Product photography session",
    Decimal("650.00"),
    10,
    False,
)


async def create(invoicer_email: str, invoice_number: str) -> int:
    settings = get_settings()
    api = PayPalInvoicesAPI(PayPalClient(PayPalTokenProvider(settings)))
    payload = build_invoice_payload(DEMO_DRAFT, invoice_number, merchant_today(), invoicer_email)
    try:
        invoice_id = await api.create_draft_invoice(payload, request_id=str(uuid.uuid4()))
        verified = await api.get_invoice(invoice_id)
    except PayPalError as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}. Nothing was retried.")
        return 1
    print(f"[created]  {invoice_number} -> {invoice_id}")
    print(f"[verified] status={verified.status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one Sandbox draft invoice for the demo.")
    parser.add_argument("--execute", action="store_true", help="Actually create the draft in PayPal Sandbox.")
    args = parser.parse_args()
    settings = get_settings()

    if settings.paypal_environment != "sandbox" or "sandbox" not in settings.paypal_base_url:
        print("Refusing to run: this script is for PayPal Sandbox only.")
        return 1
    if not settings.paypal_credentials_configured or not settings.paypal_sandbox_invoicer_email:
        print("Configure PayPal credentials and PAYPAL_SANDBOX_INVOICER_EMAIL in backend/.env")
        return 1

    number = build_invoice_number(datetime.now(MERCHANT_TIMEZONE).strftime("%y%m%d%H%M"), 90)
    print(f"Plan: create DRAFT {number} for {DEMO_DRAFT.client_name}, {DEMO_DRAFT.amount} USD, "
          f"due in {DEMO_DRAFT.due_in_days} days (invoicer {settings.paypal_sandbox_invoicer_email}).")

    if not args.execute:
        print("DRY RUN: no PayPal calls were made. Re-run with --execute to create it.")
        return 0
    if input("Type 'yes' to create this draft in PayPal Sandbox: ").strip().lower() != "yes":
        print("Cancelled. Nothing was created.")
        return 0
    return asyncio.run(create(settings.paypal_sandbox_invoicer_email, number))


if __name__ == "__main__":
    sys.exit(main())
