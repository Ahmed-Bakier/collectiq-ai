"""Tests for invoice pagination and GET /api/invoices/analysis (mocked HTTP)."""

import asyncio
from datetime import date

import httpx
from fastapi.testclient import TestClient

from app.api.dependencies import get_today
from app.integrations.paypal.dependencies import get_paypal_client
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.main import app
from app.services.invoices import InvoiceService
from tests.fakes import make_paypal_client, sample_paypal_invoice


def test_list_all_invoices_follows_pages() -> None:
    pages_requested: list[int] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages_requested.append(page)
        return httpx.Response(
            200,
            json={"items": [sample_paypal_invoice(id=f"INV2-PAGE-{page}")], "total_items": 2, "total_pages": 2},
        )

    service = InvoiceService(PayPalInvoicesAPI(make_paypal_client(api_handler)))
    invoices = asyncio.run(service.list_all_invoices())

    assert pages_requested == [1, 2]
    assert [invoice.id for invoice in invoices] == ["INV2-PAGE-1", "INV2-PAGE-2"]


def test_analysis_route_uses_paypal_data_and_business_date() -> None:
    client = make_paypal_client(
        lambda request: httpx.Response(
            200, json={"items": [sample_paypal_invoice()], "total_items": 1, "total_pages": 1}
        )
    )
    app.dependency_overrides[get_paypal_client] = lambda: client
    app.dependency_overrides[get_today] = lambda: date(2026, 11, 20)
    try:
        response = TestClient(app).get("/api/invoices/analysis")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2026-11-20"
    item = body["invoices"][0]
    assert item["collection_state"] == "overdue"  # Sample invoice is due 2026-11-15.
    assert item["days_overdue"] == 5
    assert body["summary"]["totals_by_currency"][0]["overdue_amount"] == "250.00"
