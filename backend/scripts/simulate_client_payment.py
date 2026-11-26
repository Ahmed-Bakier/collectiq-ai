"""Simulate a client paying one open invoice in PayPal Sandbox (records the full amount due).

PayPal then fires INVOICING.INVOICE.PAID to the registered webhook, so this demonstrates the
real-time flow end to end. Sandbox only, dry-run by default, --execute + typed "yes".

Usage (from backend/):
    python scripts/simulate_client_payment.py --invoice CIQ-2611040922-04            # dry-run
    python scripts/simulate_client_payment.py --invoice CIQ-2611040922-04 --execute
"""

import argparse
import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings  # noqa: E402
from app.integrations.paypal.auth import PayPalTokenProvider  # noqa: E402
from app.integrations.paypal.client import PayPalClient  # noqa: E402
from app.integrations.paypal.exceptions import PayPalAPIError, PayPalError  # noqa: E402
from app.integrations.paypal.invoices import PayPalInvoicesAPI  # noqa: E402
from app.services.invoice_analysis import COLLECTIBLE_STATUSES, collectible_amount  # noqa: E402
from app.services.invoices import InvoiceService, to_invoice_summary  # noqa: E402
from scripts.seed_sandbox_invoices import MERCHANT_TIMEZONE  # noqa: E402


async def run(settings: Settings, reference: str, execute: bool) -> int:
    api = PayPalInvoicesAPI(PayPalClient(PayPalTokenProvider(settings)))
    invoices = await InvoiceService(api).list_all_raw_invoices()
    match = next((i for i in invoices if reference in (i.id, i.detail.invoice_number if i.detail else None)), None)
    if match is None:
        print(f"No invoice with ID or number {reference}.")
        return 1

    summary = to_invoice_summary(match)
    amount = collectible_amount(summary)
    print(f"Invoice:  {summary.invoice_number} ({summary.id})")
    print(f"Client:   {summary.recipient_business_name or summary.recipient_name}")
    print(f"Status:   {summary.status}")
    print(f"Due:      {amount} {summary.currency_code}")
    if summary.status.upper() not in COLLECTIBLE_STATUSES or amount is None or not summary.currency_code:
        print("Refusing: this invoice is not open for payment.")
        return 1
    if not execute:
        print("\nDRY RUN: no PayPal calls were made. Re-run with --execute to record the payment.")
        return 0
    if input("\nThis will RECORD A PAYMENT for the full amount in PayPal Sandbox. Type 'yes' to continue: ").strip().lower() != "yes":
        print("Cancelled. Nothing was written.")
        return 0

    try:
        payment_id = await api.record_payment(
            summary.id,
            request_id=str(uuid.uuid4()),
            amount=amount,
            currency_code=summary.currency_code,
            payment_date=datetime.now(MERCHANT_TIMEZONE).date(),
            note="Client payment (CollectIQ AI Sandbox simulation).",
        )
        verified = await api.get_invoice(summary.id)
    except PayPalError as exc:
        debug_id = exc.debug_id if isinstance(exc, PayPalAPIError) else None
        print(f"[FAILED] {type(exc).__name__}: {exc} (debug_id={debug_id}). Nothing was retried.")
        return 1
    print(f"[paid]     payment {payment_id}")
    print(f"[verified] status={verified.status}")
    print("PayPal will now send INVOICING.INVOICE.PAID to your registered webhook.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate a client paying one invoice in PayPal Sandbox.")
    parser.add_argument("--invoice", required=True, help="PayPal invoice ID or invoice number.")
    parser.add_argument("--execute", action="store_true", help="Actually record the payment.")
    args = parser.parse_args()
    settings = get_settings()
    if settings.paypal_environment != "sandbox" or "sandbox" not in settings.paypal_base_url:
        print("Refusing to run: this script is for PayPal Sandbox only.")
        return 1
    if not settings.paypal_credentials_configured:
        print("PayPal credentials are not configured in backend/.env")
        return 1
    return asyncio.run(run(settings, args.invoice.strip(), args.execute))


if __name__ == "__main__":
    sys.exit(main())
