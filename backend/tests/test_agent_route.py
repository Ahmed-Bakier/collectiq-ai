"""Tests for POST /api/agent/runs (fake LLM, mocked PayPal)."""

from datetime import date

import httpx
from fastapi.testclient import TestClient

from app.agent.dependencies import get_llm
from app.agent.llm import LLMNotConfiguredError
from app.api.dependencies import get_today
from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from tests.agent_fakes import ScriptedLLM, final_answer, tool_call
from tests.fakes import make_paypal_client, sample_paypal_invoice


def paypal_client_with_one_invoice():  # type: ignore[no-untyped-def]
    return make_paypal_client(
        lambda request: httpx.Response(
            200, json={"items": [sample_paypal_invoice()], "total_items": 1, "total_pages": 1}
        )
    )


def post_run(llm_factory, payload: dict) -> httpx.Response:  # type: ignore[no-untyped-def]
    app.dependency_overrides[get_llm] = llm_factory
    app.dependency_overrides[get_paypal_client] = paypal_client_with_one_invoice
    app.dependency_overrides[get_today] = lambda: date(2026, 11, 20)
    try:
        return TestClient(app).post("/api/agent/runs", json=payload)
    finally:
        app.dependency_overrides.clear()


def test_agent_run_endpoint_returns_structured_result() -> None:
    llm = ScriptedLLM([tool_call("get_invoice_analysis", {}), final_answer("Summary text")])
    response = post_run(lambda: llm, {"message": "Analyze my invoices"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Summary text"
    assert body["status"] == "completed"
    assert body["model"] == "scripted-test-model"
    assert body["tool_calls"][0]["name"] == "get_invoice_analysis"


def test_agent_run_returns_503_when_ai_not_configured() -> None:
    def not_configured():  # type: ignore[no-untyped-def]
        raise LLMNotConfiguredError("not configured")

    response = post_run(not_configured, {"message": "Analyze my invoices"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"


def test_empty_message_is_rejected() -> None:
    response = post_run(lambda: ScriptedLLM([]), {"message": ""})
    assert response.status_code == 422
