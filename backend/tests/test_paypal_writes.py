"""Tests for PayPal write operations (mocked HTTP, no real PayPal calls)."""

import asyncio
import json

import httpx
import pytest

from app.integrations.paypal.exceptions import PayPalWriteOutcomeUnknownError
from app.integrations.paypal.invoices import INVOICES_PATH, PayPalInvoicesAPI
from tests.fakes import ApiHandler, make_paypal_client, sample_paypal_invoice

CREATED_LINK = {
    "href": "https://api-m.sandbox.paypal.com/v2/invoicing/invoices/INV2-ABCD-EFGH-IJKL-MNOP",
    "rel": "self",
    "method": "GET",
}


def make_api(
    api_handler: ApiHandler,
    token_requests: list[httpx.Request] | None = None,
) -> PayPalInvoicesAPI:
    return PayPalInvoicesAPI(make_paypal_client(api_handler, token_requests))


def test_create_draft_sends_request_id_and_parses_id_from_link() -> None:
    requests: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json=CREATED_LINK)

    invoice_id = asyncio.run(
        make_api(api_handler).create_draft_invoice({"detail": {}}, request_id="req-123")
    )

    assert invoice_id == "INV2-ABCD-EFGH-IJKL-MNOP"
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == INVOICES_PATH
    assert request.headers["PayPal-Request-Id"] == "req-123"
    assert json.loads(request.content) == {"detail": {}}


def test_create_draft_parses_id_from_full_representation() -> None:
    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "INV2-WXYZ-0000", "status": "DRAFT"})

    invoice_id = asyncio.run(make_api(api_handler).create_draft_invoice({}, request_id="r-1"))
    assert invoice_id == "INV2-WXYZ-0000"


def test_write_timeout_is_outcome_unknown_and_not_retried() -> None:
    calls: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("simulated timeout", request=request)

    with pytest.raises(PayPalWriteOutcomeUnknownError):
        asyncio.run(make_api(api_handler).send_invoice("INV2-ABCD", request_id="req-1"))
    assert len(calls) == 1  # Never retried blindly.


def test_write_401_retries_once_with_same_request_id() -> None:
    token_requests: list[httpx.Request] = []
    calls: list[httpx.Request] = []
    responses = iter([httpx.Response(401, json={}), httpx.Response(202, json=CREATED_LINK)])

    def api_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return next(responses)

    asyncio.run(make_api(api_handler, token_requests).send_invoice("INV2-ABCD", request_id="req-9"))

    assert len(calls) == 2
    assert [call.headers["PayPal-Request-Id"] for call in calls] == ["req-9", "req-9"]
    assert len(token_requests) == 2


def test_send_invoice_body_and_path() -> None:
    requests: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json=CREATED_LINK)

    asyncio.run(make_api(api_handler).send_invoice("INV2-ABCD", request_id="req-2"))

    assert requests[0].url.path == f"{INVOICES_PATH}/INV2-ABCD/send"
    assert json.loads(requests[0].content) == {"send_to_recipient": True, "send_to_invoicer": False}


def test_malformed_invoice_id_is_rejected_before_any_call() -> None:
    def api_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("PayPal must not be called")

    with pytest.raises(ValueError):
        asyncio.run(make_api(api_handler).send_invoice("../../v1/oauth2/token", request_id="r"))


def test_post_requires_request_id() -> None:
    client = make_paypal_client(lambda request: httpx.Response(201, json=CREATED_LINK))
    with pytest.raises(ValueError):
        asyncio.run(client.post(INVOICES_PATH, {}, request_id=""))


def test_get_invoice_returns_typed_model() -> None:
    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=sample_paypal_invoice())

    invoice = asyncio.run(make_api(api_handler).get_invoice("INV2-TEST-AAAA-BBBB-CCCC"))
    assert invoice.status == "UNPAID"
