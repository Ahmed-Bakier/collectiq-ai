"""Tests for the approval and execution engine (fake LLM, stateful fake PayPal, temp DB)."""

import asyncio
import json
from datetime import date, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.dependencies import get_llm
from app.api.dependencies import get_today
from app.db.models import ActionRecord
from app.db.types import utc_now
from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from tests.agent_fakes import ScriptedLLM, final_answer, tool_call
from tests.paypal_state_fake import FakeInvoiceStore

DRAFT_ID = "INV2-DRAFT-0001"
OVERDUE_ID = "INV2-OVER-0001"  # Sample invoice due 2026-11-15; today is 2026-11-20.


def propose(client: TestClient, store: FakeInvoiceStore, action_type: str) -> dict:
    llm = ScriptedLLM(
        [
            tool_call(
                "propose_action",
                {
                    "invoice_id": store.invoice_id,
                    "action_type": action_type,
                    "reason": "Backend suggested this action",
                    "message_to_client": "Hello, a short note about your invoice.",
                },
            ),
            final_answer("Proposed."),
        ]
    )
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_paypal_client] = store.client
    app.dependency_overrides[get_today] = lambda: date(2026, 11, 20)
    run = client.post("/api/agent/runs", json={"message": "Check invoices"}).json()
    return run["proposed_actions"][0]


def approve(client: TestClient, action_id: str) -> httpx.Response:
    action = client.get(f"/api/actions/{action_id}").json()
    return client.post(f"/api/actions/{action_id}/approve", json={"parameters_hash": action["parameters_hash"]})


def audit_types(client: TestClient, action_id: str) -> list[str]:
    return [event["event_type"] for event in client.get(f"/api/audit?action_id={action_id}").json()["items"]]


def test_full_flow_approve_execute_verify() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]

    assert approve(client, action_id).json()["approval_status"] == "approved"
    result = client.post(f"/api/actions/{action_id}/execute").json()

    assert result["execution_status"] == "succeeded"
    assert result["verification_status"] == "verified"
    assert store.status == "SENT"
    assert len(store.writes) == 1
    assert store.writes[0].headers["PayPal-Request-Id"] == action_id
    assert json.loads(store.writes[0].content)["note"] == "Hello, a short note about your invoice."
    assert {"action_approved", "execution_started", "verification_completed", "execution_succeeded"} <= set(
        audit_types(client, action_id)
    )


def test_execute_without_approval_is_rejected() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]

    response = client.post(f"/api/actions/{action_id}/execute")

    assert response.status_code == 409
    assert store.writes == []


def test_rejected_action_can_never_execute() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]

    rejected = client.post(f"/api/actions/{action_id}/reject", json={"reason": "Not now"}).json()

    assert rejected["approval_status"] == "rejected"
    assert approve(client, action_id).status_code == 409
    assert client.post(f"/api/actions/{action_id}/execute").status_code == 409
    assert store.writes == []
    assert "action_rejected" in audit_types(client, action_id)


def test_approval_requires_matching_parameters_hash() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]

    response = client.post(f"/api/actions/{action_id}/approve", json={"parameters_hash": "0" * 64})

    assert response.status_code == 409
    assert client.get(f"/api/actions/{action_id}").json()["approval_status"] == "pending"


def test_action_executes_only_once() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]
    approve(client, action_id)

    client.post(f"/api/actions/{action_id}/execute")
    second = client.post(f"/api/actions/{action_id}/execute")

    assert second.status_code == 409
    assert len(store.writes) == 1


def test_execution_blocked_when_invoice_is_no_longer_a_draft() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]
    approve(client, action_id)
    store.status = "SENT"  # Someone sent it from the PayPal dashboard meanwhile.

    result = client.post(f"/api/actions/{action_id}/execute").json()

    assert result["execution_status"] == "failed"
    assert "Nothing was sent" in result["failure_reason"]
    assert store.writes == []
    assert "execution_blocked" in audit_types(client, action_id)


def test_paypal_rejection_marks_action_failed() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT", send_behavior="reject")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]
    approve(client, action_id)

    result = client.post(f"/api/actions/{action_id}/execute").json()

    assert result["execution_status"] == "failed"
    assert "HTTP 422" in result["failure_reason"]


def test_ambiguous_timeout_is_recorded_and_not_retried() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT", send_behavior="timeout")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]
    approve(client, action_id)

    result = client.post(f"/api/actions/{action_id}/execute").json()

    assert result["execution_status"] == "outcome_unknown"
    assert len(store.writes) == 1
    assert client.post(f"/api/actions/{action_id}/execute").status_code == 409


def test_timeout_after_paypal_applied_is_confirmed_by_verification() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT", send_behavior="timeout_after_apply")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]
    approve(client, action_id)

    result = client.post(f"/api/actions/{action_id}/execute").json()

    assert result["execution_status"] == "succeeded"
    assert result["verification_status"] == "verified"


def test_reminder_flow_for_overdue_invoice() -> None:
    store = FakeInvoiceStore(OVERDUE_ID, "SENT")
    client = TestClient(app)
    action_id = propose(client, store, "send_reminder")["id"]
    approve(client, action_id)

    result = client.post(f"/api/actions/{action_id}/execute").json()

    assert result["execution_status"] == "succeeded"
    assert result["verification_status"] == "verified"
    assert store.writes[0].url.path.endswith(f"/{OVERDUE_ID}/remind")
    body = json.loads(store.writes[0].content)
    assert body["note"] == "Hello, a short note about your invoice."
    assert body["subject"].startswith("Payment reminder")


def test_stale_approval_cannot_execute(db_sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store, "send_invoice")["id"]
    approve(client, action_id)

    async def age_approval() -> None:
        async with db_sessionmaker() as session:
            action = await session.get(ActionRecord, action_id)
            assert action is not None
            action.decided_at = utc_now() - timedelta(minutes=20)
            await session.commit()

    asyncio.run(age_approval())

    assert client.post(f"/api/actions/{action_id}/execute").status_code == 409
    assert store.writes == []
