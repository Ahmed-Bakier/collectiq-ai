"""PayPal webhooks: signature verification, idempotency, re-read from PayPal, withdrawal of pending actions."""

import json
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.dependencies import get_optional_llm
from app.api.dependencies import get_today
from app.core.config import get_settings
from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from tests.fakes import make_paypal_client
from tests.paypal_state_fake import FakeInvoiceBook, invoice_json
from tests.test_autopilot import drafting_llm

TODAY = date(2026, 11, 20)
INVOICE_ID = "INV2-PAID-0001"
VERIFY_PATH = "/v1/notifications/verify-webhook-signature"
HEADERS = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "paypal-transmission-id": "TRANSMISSION-1",
    "paypal-transmission-sig": "signature",
    "paypal-transmission-time": "2026-11-20T10:00:00Z",
}


def paid_event(event_id: str = "WH-EVENT-1") -> dict[str, Any]:
    return {"id": event_id, "event_type": "INVOICING.INVOICE.PAID", "resource": {"id": INVOICE_ID, "status": "PAID"}}


def setup(
    monkeypatch: pytest.MonkeyPatch, verification: str = "SUCCESS"
) -> tuple[TestClient, FakeInvoiceBook, list[dict[str, Any]]]:
    monkeypatch.setattr(get_settings(), "paypal_webhook_id", "WH-TEST")
    book = FakeInvoiceBook([invoice_json(INVOICE_ID, "SENT", "2026-11-17", "250.00", "Small Co")])
    verify_calls: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == VERIFY_PATH:
            verify_calls.append(json.loads(request.content))
            return httpx.Response(200, json={"verification_status": verification})
        return book.handle(request)

    app.dependency_overrides[get_paypal_client] = lambda: make_paypal_client(handle)
    app.dependency_overrides[get_optional_llm] = lambda: drafting_llm(1)
    app.dependency_overrides[get_today] = lambda: TODAY
    return TestClient(app), book, verify_calls


def mark_paid(book: FakeInvoiceBook) -> None:
    invoice = book.invoices[INVOICE_ID]
    invoice["status"] = "PAID"
    invoice["due_amount"] = {"currency_code": "USD", "value": "0.00"}
    invoice["payments"] = {"paid_amount": {"currency_code": "USD", "value": "250.00"}, "transactions": []}


def post(client: TestClient, event: dict[str, Any]) -> httpx.Response:
    return client.post("/api/webhooks/paypal", content=json.dumps(event), headers=HEADERS)


def test_paid_event_records_payment_and_withdraws_pending_reminder(monkeypatch: pytest.MonkeyPatch) -> None:
    client, book, verify_calls = setup(monkeypatch)
    action_id = client.post("/api/autopilot/run").json()["proposals"][0]["action"]["id"]
    mark_paid(book)

    response = post(client, paid_event())

    assert response.json() == {"status": "processed", "event_type": "INVOICING.INVOICE.PAID", "invoice_id": INVOICE_ID}
    assert client.get(f"/api/actions/{action_id}").json()["approval_status"] == "superseded"
    events = client.get("/api/audit?limit=200").json()["items"]
    payment = next(event for event in events if event["event_type"] == "payment_received")
    assert "250.00 USD" in payment["message"]
    assert payment["actor"] == "system"
    assert verify_calls[0]["webhook_id"] == "WH-TEST"
    assert verify_calls[0]["webhook_event"]["id"] == "WH-EVENT-1"
    assert verify_calls[0]["transmission_id"] == "TRANSMISSION-1"


def test_unsigned_event_is_rejected_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    client, book, _ = setup(monkeypatch, verification="FAILURE")
    mark_paid(book)

    response = post(client, paid_event())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "webhook_rejected"
    events = client.get("/api/audit?limit=200").json()["items"]
    assert not any(event["event_type"] == "payment_received" for event in events)


def test_duplicate_event_is_processed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    client, book, verify_calls = setup(monkeypatch)
    mark_paid(book)

    assert post(client, paid_event()).json()["status"] == "processed"
    assert post(client, paid_event()).json()["status"] == "duplicate"
    assert len(verify_calls) == 1
    events = client.get("/api/audit?limit=200").json()["items"]
    assert sum(event["event_type"] == "payment_received" for event in events) == 1


def test_webhooks_require_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, verify_calls = setup(monkeypatch)
    monkeypatch.setattr(get_settings(), "paypal_webhook_id", None)

    response = post(client, paid_event())

    assert response.status_code == 503
    assert verify_calls == []
