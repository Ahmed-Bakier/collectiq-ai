"""Tests for the PayPal invoices adapter and invoice service (mocked HTTP)."""

import asyncio
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.integrations.paypal.exceptions import PayPalAPIError
from app.integrations.paypal.invoices import INVOICES_PATH, PayPalInvoicesAPI
from app.services.invoices import InvoiceService
from tests.fakes import ApiHandler, FAKE_ACCESS_TOKEN, make_paypal_client, sample_paypal_invoice


def make_service(
    api_handler: ApiHandler,
    token_requests: list[httpx.Request] | None = None,
) -> InvoiceService:
    return InvoiceService(PayPalInvoicesAPI(make_paypal_client(api_handler, token_requests)))


def test_list_invoices_sends_expected_request_and_maps_fields() -> None:
    requests: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"items": [sample_paypal_invoice()], "total_items": 1, "total_pages": 1},
        )

    result = asyncio.run(make_service(api_handler).list_invoices(page=2, page_size=10))

    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == INVOICES_PATH
    assert request.url.params["page"] == "2"
    assert request.url.params["page_size"] == "10"
    assert request.url.params["total_required"] == "true"
    assert request.headers["Authorization"] == f"Bearer {FAKE_ACCESS_TOKEN}"

    assert result.total_items == 1
    assert result.source == "paypal_sandbox"
    invoice = result.items[0]
    assert invoice.id == "INV2-TEST-AAAA-BBBB-CCCC"
    assert invoice.status == "UNPAID"
    assert invoice.recipient_name == "Jane Doe"
    assert invoice.recipient_email == "jane@example.com"
    assert invoice.currency_code == "USD"
    assert invoice.total_amount == Decimal("250.00")
    assert invoice.amount_due == Decimal("250.00")
    assert invoice.invoice_date == date(2026, 11, 1)
    assert invoice.due_date == date(2026, 11, 15)


def test_missing_optional_fields_stay_none() -> None:
    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [{"id": "INV2-MIN", "status": "DRAFT"}]})

    invoice = asyncio.run(make_service(api_handler).list_invoices(1, 20)).items[0]

    assert invoice.due_date is None
    assert invoice.total_amount is None
    assert invoice.recipient_name is None


def test_empty_invoice_list() -> None:
    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total_items": 0, "total_pages": 0})

    result = asyncio.run(make_service(api_handler).list_invoices(1, 20))
    assert result.items == []


def test_expired_token_is_refreshed_once() -> None:
    token_requests: list[httpx.Request] = []
    responses = iter(
        [
            httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"}),
            httpx.Response(200, json={"items": []}),
        ]
    )

    def api_handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    asyncio.run(make_service(api_handler, token_requests).list_invoices(1, 20))
    assert len(token_requests) == 2


def test_paypal_error_raises_api_error_with_debug_id() -> None:
    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"name": "INTERNAL_SERVER_ERROR", "message": "Something went wrong"},
            headers={"paypal-debug-id": "dbg-123"},
        )

    with pytest.raises(PayPalAPIError) as exc_info:
        asyncio.run(make_service(api_handler).list_invoices(1, 20))

    assert exc_info.value.status_code == 500
    assert exc_info.value.debug_id == "dbg-123"
