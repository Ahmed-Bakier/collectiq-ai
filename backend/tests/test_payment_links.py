"""Payment link + QR: only PayPal's own page for that exact, payable invoice."""

from typing import Any

from fastapi.testclient import TestClient

from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from app.services.payment_links import is_paypal_invoice_url
from tests.paypal_state_fake import FakeInvoiceBook, invoice_json

SENT_ID = "INV2-LINK-0001"
DRAFT_ID = "INV2-LINK-0002"
EVIL_ID = "INV2-LINK-0003"
PAY_URL = f"https://www.sandbox.paypal.com/invoice/p/#{SENT_ID}"


def with_url(invoice: dict[str, Any], url: str) -> dict[str, Any]:
    invoice["detail"]["metadata"] = {"recipient_view_url": url}
    return invoice


def client() -> TestClient:
    book = FakeInvoiceBook(
        [
            with_url(invoice_json(SENT_ID, "SENT", "2026-11-17", "450.00", "Northwind"), PAY_URL),
            with_url(invoice_json(DRAFT_ID, "DRAFT", "2026-11-30", "650.00", "Harbor"), f"https://www.sandbox.paypal.com/invoice/p/#{DRAFT_ID}"),
            with_url(invoice_json(EVIL_ID, "SENT", "2026-11-17", "100.00", "Evil"), f"https://pay-paypal.example.net/invoice/p/#{EVIL_ID}"),
        ]
    )
    app.dependency_overrides[get_paypal_client] = book.client
    return TestClient(app)


def test_sent_invoice_returns_paypal_link_and_qr() -> None:
    body = client().get(f"/api/invoices/{SENT_ID}/payment-link").json()

    assert body["pay_url"] == PAY_URL
    assert body["client"] == "Northwind"
    assert body["amount_due"] == "450.00"
    assert body["qr_svg_data_uri"].startswith("data:image/svg+xml")


def test_draft_invoice_has_no_payment_link() -> None:
    response = client().get(f"/api/invoices/{DRAFT_ID}/payment-link")

    assert response.status_code == 409


def test_non_paypal_link_is_refused() -> None:
    response = client().get(f"/api/invoices/{EVIL_ID}/payment-link")

    assert response.status_code == 409


def test_invalid_invoice_id_is_rejected() -> None:
    assert client().get("/api/invoices/not..valid/payment-link").status_code in (400, 404)


def test_url_validation_rules() -> None:
    assert is_paypal_invoice_url(PAY_URL, SENT_ID)
    assert not is_paypal_invoice_url(PAY_URL.replace("https", "http"), SENT_ID)
    assert not is_paypal_invoice_url(PAY_URL, "INV2-OTHER-0001")
    assert not is_paypal_invoice_url("https://www.sandbox.paypal.com.evil.net/invoice/p/#" + SENT_ID, SENT_ID)
    assert not is_paypal_invoice_url("https://user@www.sandbox.paypal.com/invoice/p/#" + SENT_ID, SENT_ID)


def test_paypal_compact_fragment_format_is_accepted() -> None:
    real = "https://www.sandbox.paypal.com/invoice/p/#3U7HDN6DQQQXXGHT"  # As returned by PayPal Sandbox.
    assert is_paypal_invoice_url(real, "INV2-3U7H-DN6D-QQQX-XGHT")
    assert not is_paypal_invoice_url(real, "INV2-AAAA-BBBB-CCCC-DDDD")
