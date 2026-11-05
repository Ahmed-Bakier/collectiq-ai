"""Tests for client payment intelligence and the collections forecast."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.api.dependencies import get_today
from app.integrations.paypal.dependencies import get_paypal_client
from app.integrations.paypal.invoices import INVOICES_PATH, PayPalInvoicesAPI
from app.integrations.paypal.schemas import PayPalInvoice
from app.main import app
from app.schemas.insights import RiskLevel
from app.services.client_insights import build_insights
from tests.fakes import make_paypal_client
from tests.paypal_state_fake import invoice_json

TODAY = date(2026, 11, 20)
TZ = "America/Los_Angeles"


def paid_invoice(
    invoice_id: str, client: str, due: str, paid_on: str, amount: str = "400.00", with_payments: bool = True
) -> dict[str, Any]:
    data = invoice_json(invoice_id, "PAID", due, amount, client)
    data["due_amount"] = {"currency_code": "USD", "value": "0.00"}
    if with_payments:
        data["payments"] = {
            "paid_amount": {"currency_code": "USD", "value": amount},
            "transactions": [
                {
                    "payment_id": "EXTR-TEST",
                    "payment_date": paid_on,
                    "method": "BANK_TRANSFER",
                    "type": "EXTERNAL",
                    "amount": {"currency_code": "USD", "value": amount},
                }
            ],
        }
    return data


def portfolio() -> list[PayPalInvoice]:
    raw = [
        paid_invoice("INV2-REL1-0001", "Reliable Co", "2026-09-15", "2026-09-14"),
        paid_invoice("INV2-REL2-0001", "Reliable Co", "2026-10-15", "2026-10-15"),
        paid_invoice("INV2-SLW1-0001", "Slow Co", "2026-09-01", "2026-09-26"),  # 25 days late
        paid_invoice("INV2-SLW2-0001", "Slow Co", "2026-10-01", "2026-10-21"),  # 20 days late
        paid_invoice("INV2-MID1-0001", "Mid Co", "2026-09-10", "2026-09-15"),  # 5 days late
        paid_invoice("INV2-MID2-0001", "Mid Co", "2026-10-10", "2026-10-11"),  # 1 day late
        invoice_json("INV2-RELO-0001", "SENT", "2026-11-25", "500.00", "Reliable Co"),
        invoice_json("INV2-SLWO-0001", "SENT", "2026-11-22", "900.00", "Slow Co"),
        invoice_json("INV2-NEWO-0001", "SENT", "2026-12-30", "300.00", "New Co"),
        invoice_json("INV2-DRFT-0001", "DRAFT", "2026-12-01", "700.00", "Draft Co"),
    ]
    return [PayPalInvoice.model_validate(item) for item in raw]


def test_risk_levels_from_payment_history() -> None:
    result = build_insights(portfolio(), TODAY, TZ)
    clients = {insight.client: insight for insight in result.clients}

    assert [insight.client for insight in result.clients] == ["Slow Co", "Mid Co", "New Co", "Reliable Co"]
    assert clients["Reliable Co"].risk_level is RiskLevel.LOW
    assert clients["Reliable Co"].on_time_rate == 1.0
    assert clients["Slow Co"].risk_level is RiskLevel.HIGH
    assert clients["Slow Co"].avg_days_late == 22.5
    assert clients["Mid Co"].risk_level is RiskLevel.MEDIUM
    assert clients["New Co"].risk_level is RiskLevel.NEW
    assert "Draft Co" not in clients  # Drafts are not part of client behaviour.


def test_forecast_shifts_expected_dates_by_client_habits() -> None:
    forecast = build_insights(portfolio(), TODAY, TZ).forecast
    rows = {row.invoice_id: row for row in forecast.invoices}

    assert forecast.currency_code == "USD"
    assert forecast.total_open == Decimal("1700")
    assert rows["INV2-RELO-0001"].expected_date == date(2026, 11, 25)
    assert rows["INV2-SLWO-0001"].expected_date == date(2026, 12, 14)  # Due 11-22 + 22 days.
    assert rows["INV2-SLWO-0001"].at_risk is True
    assert forecast.buckets[0].expected_amount == Decimal("500")
    assert forecast.buckets[3].at_risk_amount == Decimal("900")
    assert forecast.expected_later == Decimal("300")
    assert forecast.at_risk_amount == Decimal("900")
    assert forecast.expected_within_horizon == Decimal("1400")


def test_long_overdue_new_client_is_high_risk_and_expected_from_today() -> None:
    old = PayPalInvoice.model_validate(invoice_json("INV2-OLD1-0001", "SENT", "2026-10-10", "250.00", "Old Co"))

    result = build_insights([old], TODAY, TZ)

    insight = result.clients[0]
    assert insight.risk_level is RiskLevel.HIGH
    assert insight.oldest_overdue_days == 41
    assert any("41 days overdue" in reason for reason in insight.risk_reasons)
    assert result.forecast.invoices[0].expected_date == TODAY
    assert result.forecast.buckets[0].at_risk_amount == Decimal("250")


def test_route_reads_payment_dates_from_invoice_details() -> None:
    listed = paid_invoice("INV2-DET1-0001", "Detail Co", "2026-10-01", "2026-09-30", with_payments=False)
    detail = paid_invoice("INV2-DET1-0001", "Detail Co", "2026-10-01", "2026-09-30")
    detail_calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == INVOICES_PATH:
            return httpx.Response(200, json={"items": [listed], "total_items": 1, "total_pages": 1})
        if request.method == "GET" and request.url.path == f"{INVOICES_PATH}/INV2-DET1-0001":
            detail_calls.append(request.url.path)
            return httpx.Response(200, json=detail)
        raise AssertionError(f"Unexpected PayPal call: {request.method} {request.url.path}")

    app.dependency_overrides[get_paypal_client] = lambda: make_paypal_client(handle)
    app.dependency_overrides[get_today] = lambda: TODAY

    response = TestClient(app).get("/api/insights")

    assert response.status_code == 200
    client = response.json()["clients"][0]
    assert client["paid_count"] == 1
    assert client["on_time_rate"] == 1.0
    assert client["risk_level"] == "low"
    assert len(detail_calls) == 1


def test_record_payment_request() -> None:
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"payment_id": "EXTR-TEST123"})

    api = PayPalInvoicesAPI(make_paypal_client(handle))
    payment_id = asyncio.run(
        api.record_payment(
            "INV2-PAY1-0001",
            "request-123",
            amount=Decimal("450"),
            currency_code="USD",
            payment_date=date(2026, 10, 19),
        )
    )

    request = next(item for item in captured if item.url.path.endswith("/payments"))
    assert payment_id == "EXTR-TEST123"
    assert request.url.path == f"{INVOICES_PATH}/INV2-PAY1-0001/payments"
    assert request.headers["PayPal-Request-Id"] == "request-123"
    assert json.loads(request.content) == {
        "method": "BANK_TRANSFER",
        "payment_date": "2026-10-19",
        "amount": {"currency_code": "USD", "value": "450.00"},
    }


def test_payment_history_seed_plan_is_valid() -> None:
    from scripts.seed_payment_history import CLIENTS, HISTORY

    assert all(item.client_name in CLIENTS for item in HISTORY)
    assert all(item.invoice_date < item.payment_date <= date(2026, 11, 5) for item in HISTORY)
