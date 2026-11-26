"""A minimal stateful fake of the PayPal invoice API for approval tests."""

from typing import Any

import httpx

from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.invoices import INVOICES_PATH
from tests.fakes import make_paypal_client, sample_paypal_invoice


class FakeInvoiceStore:
    """Holds one invoice. send_behavior: ok | reject | timeout | timeout_after_apply."""

    def __init__(self, invoice_id: str, status: str, send_behavior: str = "ok") -> None:
        self.invoice_id = invoice_id
        self.status = status
        self.send_behavior = send_behavior
        self.writes: list[httpx.Request] = []

    def invoice(self) -> dict[str, Any]:
        return sample_paypal_invoice(id=self.invoice_id, status=self.status)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == INVOICES_PATH:
            return httpx.Response(200, json={"items": [self.invoice()], "total_items": 1, "total_pages": 1})
        if request.method == "GET" and path == f"{INVOICES_PATH}/{self.invoice_id}":
            return httpx.Response(200, json=self.invoice())
        if request.method == "POST" and path.endswith("/send"):
            self.writes.append(request)
            return self._send(request)
        if request.method == "POST" and path.endswith("/remind"):
            self.writes.append(request)
            return httpx.Response(204)
        raise AssertionError(f"Unexpected PayPal call: {request.method} {path}")

    def _send(self, request: httpx.Request) -> httpx.Response:
        if self.send_behavior == "reject":
            return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "message": "Cannot send."})
        if self.send_behavior == "timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        self.status = "SENT"
        if self.send_behavior == "timeout_after_apply":
            raise httpx.ReadTimeout("simulated timeout after PayPal applied the change", request=request)
        return httpx.Response(202, json={"href": f"https://api-m.sandbox.paypal.com{INVOICES_PATH}/{self.invoice_id}"})

    def client(self) -> PayPalClient:
        return make_paypal_client(self.handle)


def invoice_json(invoice_id: str, status: str, due_date: str, amount: str, client: str) -> dict[str, Any]:
    """A minimal PayPal invoice payload (fake data)."""
    return {
        "id": invoice_id,
        "status": status,
        "detail": {
            "invoice_number": f"CIQ-{invoice_id[-4:]}",
            "invoice_date": "2026-11-01",
            "currency_code": "USD",
            "payment_term": {"due_date": due_date},
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": "Sam", "surname": "Lee"},
                    "business_name": client,
                    "email_address": "sam@example.com",
                }
            }
        ],
        "amount": {"currency_code": "USD", "value": amount},
        "due_amount": {"currency_code": "USD", "value": amount},
    }


class FakeInvoiceBook:
    """Stateful fake with several invoices (list, get, send, remind)."""

    def __init__(self, invoices: list[dict[str, Any]]) -> None:
        self.invoices = {invoice["id"]: invoice for invoice in invoices}
        self.writes: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == INVOICES_PATH:
            items = list(self.invoices.values())
            return httpx.Response(200, json={"items": items, "total_items": len(items), "total_pages": 1})
        if request.method == "GET" and path.startswith(f"{INVOICES_PATH}/"):
            invoice = self.invoices.get(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=invoice) if invoice else httpx.Response(404, json={})
        if request.method == "POST" and path.endswith("/send"):
            self.writes.append(request)
            self.invoices[path.split("/")[-2]]["status"] = "SENT"
            return httpx.Response(202, json={"href": f"https://api-m.sandbox.paypal.com{path}"})
        if request.method == "POST" and path.endswith("/remind"):
            self.writes.append(request)
            return httpx.Response(204)
        raise AssertionError(f"Unexpected PayPal call: {request.method} {path}")

    def client(self) -> PayPalClient:
        return make_paypal_client(self.handle)
