"""Seed PayPal Sandbox with PAID invoice history for client payment intelligence.

Creates past invoices for the demo clients, sends them and records an external
payment (bank transfer) on each, following a realistic payment habit per client.

Safety rules:
- Sandbox only; dry-run by default (prints the plan, makes NO PayPal calls).
- Writes only with --execute AND an interactive "yes" confirmation.
- Unique PayPal-Request-Id per write; stops on the first failure (no retries).

Usage (from backend/):
    python scripts/seed_payment_history.py                       # dry-run
    python scripts/seed_payment_history.py --execute --limit 1   # first invoice only (test)
    python scripts/seed_payment_history.py --execute --from 2    # the rest
"""

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings  # noqa: E402
from app.integrations.paypal.auth import PayPalTokenProvider  # noqa: E402
from app.integrations.paypal.client import PayPalClient  # noqa: E402
from app.integrations.paypal.exceptions import PayPalAPIError, PayPalError  # noqa: E402
from app.integrations.paypal.invoices import PayPalInvoicesAPI  # noqa: E402
from scripts.seed_sandbox_invoices import (  # noqa: E402
    CURRENCY,
    MERCHANT_TIMEZONE,
    SEED_INVOICES,
    SeedInvoice,
    build_invoice_number,
    build_invoice_payload,
)

TERM_DAYS = 14
PAYMENT_NOTE = "CollectIQ AI demo payment history (PayPal Sandbox)."
CLIENTS = {seed.client_name: seed for seed in SEED_INVOICES}


@dataclass(frozen=True)
class HistoryInvoice:
    client_name: str
    description: str
    amount: Decimal
    invoice_date: date
    paid_offset_days: int  # Payment date relative to the due date (negative = early).

    @property
    def due_date(self) -> date:
        return self.invoice_date + timedelta(days=TERM_DAYS)

    @property
    def payment_date(self) -> date:
        return self.due_date + timedelta(days=self.paid_offset_days)


def _h(client: str, description: str, amount: str, invoice_date: str, offset: int) -> HistoryInvoice:
    return HistoryInvoice(client, description, Decimal(amount), date.fromisoformat(invoice_date), offset)


# Payment habits: Acme reliable, Northwind a bit late, Blue Harbor chronically late,
# Pixel & Co early, Lumen mixed. Harbor & Pine stays a new client (no history).
HISTORY: tuple[HistoryInvoice, ...] = (
    _h("Acme Design Studio", "Logo refresh", "900.00", "2026-08-03", -2),
    _h("Acme Design Studio", "Brand guidelines", "650.00", "2026-09-01", 0),
    _h("Acme Design Studio", "Packaging mockups", "1100.00", "2026-10-01", -1),
    _h("Northwind Traders", "Website maintenance - August", "450.00", "2026-08-01", 6),
    _h("Northwind Traders", "Website maintenance - September", "450.00", "2026-09-01", 9),
    _h("Northwind Traders", "Hosting migration", "300.00", "2026-10-01", 4),
    _h("Blue Harbor Cafe", "Seasonal menu design", "520.00", "2026-08-05", 22),
    _h("Blue Harbor Cafe", "Instagram content pack", "380.00", "2026-09-02", 18),
    _h("Blue Harbor Cafe", "Window signage", "640.00", "2026-09-20", 27),
    _h("Pixel & Co", "Blog copywriting", "250.00", "2026-08-20", -5),
    _h("Pixel & Co", "Email sequence", "400.00", "2026-09-25", -3),
    _h("Lumen Analytics", "Analytics workshop", "1800.00", "2026-08-10", 0),
    _h("Lumen Analytics", "Data pipeline review", "2100.00", "2026-09-08", 15),
    _h("Lumen Analytics", "KPI dashboard prototype", "1500.00", "2026-10-05", 2),
)


def to_seed(item: HistoryInvoice) -> SeedInvoice:
    contact = CLIENTS[item.client_name]
    return SeedInvoice(
        item.client_name,
        contact.contact_given_name,
        contact.contact_surname,
        contact.contact_email,
        item.description,
        item.amount,
        TERM_DAYS,
        True,
    )


def select(start: int, limit: int | None) -> list[tuple[int, HistoryInvoice]]:
    items = list(enumerate(HISTORY, start=1))[start - 1 :]
    return items[:limit] if limit else items


def print_plan(settings: Settings, items: list[tuple[int, HistoryInvoice]]) -> None:
    print("CollectIQ AI - PayPal Sandbox payment history plan")
    print(f"PayPal URL: {settings.paypal_base_url}\n")
    print(f"{'#':<4}{'Client':<21}{'Amount':>10}  {'Invoice':<11} {'Due':<11} {'Paid':<11} Days late")
    for index, item in items:
        late = (item.payment_date - item.due_date).days
        print(
            f"{index:<4}{item.client_name:<21}{item.amount:>10}  {item.invoice_date.isoformat():<11} "
            f"{item.due_date.isoformat():<11} {item.payment_date.isoformat():<11} {late:+d}"
        )


async def execute(settings: Settings, items: list[tuple[int, HistoryInvoice]], batch_stamp: str) -> int:
    api = PayPalInvoicesAPI(PayPalClient(PayPalTokenProvider(settings)))
    invoicer_email = settings.paypal_sandbox_invoicer_email or ""

    for index, item in items:
        number = build_invoice_number(batch_stamp, index)
        payload = build_invoice_payload(to_seed(item), number, item.invoice_date, invoicer_email)
        try:
            invoice_id = await api.create_draft_invoice(payload, request_id=str(uuid.uuid4()))
            print(f"[created]  #{index} {number} -> {invoice_id}")
            await api.send_invoice(invoice_id, request_id=str(uuid.uuid4()))
            print(f"[sent]     {invoice_id}")
            payment_id = await api.record_payment(
                invoice_id,
                request_id=str(uuid.uuid4()),
                amount=item.amount,
                currency_code=CURRENCY,
                payment_date=item.payment_date,
                note=PAYMENT_NOTE,
            )
            print(f"[paid]     {invoice_id} on {item.payment_date} (payment {payment_id})")
            verified = await api.get_invoice(invoice_id)
            print(f"[verified] {invoice_id} status={verified.status}")
        except PayPalError as exc:
            debug_id = exc.debug_id if isinstance(exc, PayPalAPIError) else None
            print(f"[FAILED]   #{index} {number}: {type(exc).__name__}: {exc} (debug_id={debug_id})")
            print("Stopped. Nothing was retried. Check the Sandbox dashboard before re-running.")
            return 1

    print("\nDone. Payment history was created and verified.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PayPal Sandbox with paid invoice history.")
    parser.add_argument("--execute", action="store_true", help="Actually write to PayPal Sandbox.")
    parser.add_argument("--from", dest="start", type=int, default=1, help="First history item (1-based).")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of items.")
    args = parser.parse_args()
    settings = get_settings()

    if settings.paypal_environment != "sandbox" or "sandbox" not in settings.paypal_base_url:
        print("Refusing to run: this script is for PayPal Sandbox only.")
        return 1
    if not settings.paypal_credentials_configured or not settings.paypal_sandbox_invoicer_email:
        print("Configure PayPal credentials and PAYPAL_SANDBOX_INVOICER_EMAIL in backend/.env")
        return 1
    if args.start < 1 or (args.limit is not None and args.limit < 1):
        print("--from and --limit must be 1 or greater.")
        return 1

    items = select(args.start, args.limit)
    if not items:
        print("Nothing selected.")
        return 0
    today = datetime.now(MERCHANT_TIMEZONE).date()
    if any(item.payment_date > today for _, item in items):
        print("Refusing to run: a payment date is in the future.")
        return 1

    print_plan(settings, items)
    if not args.execute:
        print("\nDRY RUN: no PayPal calls were made. Re-run with --execute to write these invoices.")
        return 0

    answer = input(
        f"\nThis will CREATE, SEND and RECORD A PAYMENT for {len(items)} invoice(s) in PayPal Sandbox "
        f"({len(items) * 3} writes).\nType 'yes' to continue: "
    )
    if answer.strip().lower() != "yes":
        print("Cancelled. Nothing was written.")
        return 0

    batch_stamp = "H" + datetime.now(MERCHANT_TIMEZONE).strftime("%y%m%d%H%M")
    return asyncio.run(execute(settings, items, batch_stamp))


if __name__ == "__main__":
    sys.exit(main())
