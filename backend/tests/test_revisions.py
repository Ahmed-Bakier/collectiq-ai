"""Tests for editing and AI-redrafting proposed actions (fake LLM, fake PayPal, temp DB)."""

import json
from datetime import date

from fastapi.testclient import TestClient

from app.agent.dependencies import get_llm
from app.api.dependencies import get_today
from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from tests.agent_fakes import ScriptedLLM, final_answer, tool_call
from tests.paypal_state_fake import FakeInvoiceStore

DRAFT_ID = "INV2-DRAFT-0001"
ORIGINAL_NOTE = "Hello, a short note about your invoice."
EDITED_NOTE = "Hi Jane, here is your invoice. Thank you!"


def propose(client: TestClient, store: FakeInvoiceStore) -> str:
    llm = ScriptedLLM(
        [
            tool_call(
                "propose_action",
                {
                    "invoice_id": store.invoice_id,
                    "action_type": "send_invoice",
                    "reason": "Draft not sent yet",
                    "message_to_client": ORIGINAL_NOTE,
                },
            ),
            final_answer("Proposed."),
        ]
    )
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_paypal_client] = store.client
    app.dependency_overrides[get_today] = lambda: date(2026, 11, 20)
    return client.post("/api/agent/runs", json={"message": "Check invoices"}).json()["proposed_actions"][0]["id"]


def test_user_edit_creates_new_version_that_needs_new_approval() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    old_id = propose(client, store)
    old = client.get(f"/api/actions/{old_id}").json()

    response = client.post(f"/api/actions/{old_id}/revise", json={"message_to_client": EDITED_NOTE})

    assert response.status_code == 200
    new = response.json()
    assert new["id"] != old_id
    assert new["approval_status"] == "pending"
    assert new["parameters"]["note"] == EDITED_NOTE
    assert new["parameters_hash"] != old["parameters_hash"]
    assert client.get(f"/api/actions/{old_id}").json()["approval_status"] == "superseded"

    # The old version can no longer be approved.
    old_approval = client.post(f"/api/actions/{old_id}/approve", json={"parameters_hash": old["parameters_hash"]})
    assert old_approval.status_code == 409

    # The new version is approved and executed with the edited message.
    approval = client.post(f"/api/actions/{new['id']}/approve", json={"parameters_hash": new["parameters_hash"]})
    assert approval.status_code == 200
    client.post(f"/api/actions/{new['id']}/execute")
    assert json.loads(store.writes[0].content)["note"] == EDITED_NOTE

    events = client.get(f"/api/audit?action_id={new['id']}").json()["items"]
    revised = next(event for event in events if event["event_type"] == "action_revised")
    assert revised["actor"] == "user"


def test_cannot_edit_after_approval() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store)
    action = client.get(f"/api/actions/{action_id}").json()
    client.post(f"/api/actions/{action_id}/approve", json={"parameters_hash": action["parameters_hash"]})

    response = client.post(f"/api/actions/{action_id}/revise", json={"message_to_client": EDITED_NOTE})

    assert response.status_code == 409


def test_unchanged_message_is_rejected() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store)

    response = client.post(f"/api/actions/{action_id}/revise", json={"message_to_client": ORIGINAL_NOTE})

    assert response.status_code == 409


def test_ai_redraft_uses_requested_tone_and_language() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    old_id = propose(client, store)
    arabic_text = "مرحبًا، نرجو تسديد الفاتورة في أقرب وقت. شكرًا لكم."
    drafting_llm = ScriptedLLM([final_answer(arabic_text)])
    app.dependency_overrides[get_llm] = lambda: drafting_llm

    response = client.post(f"/api/actions/{old_id}/redraft", json={"tone": "firm", "language": "ar"})

    assert response.status_code == 200
    new = response.json()
    assert new["message_to_client"] == arabic_text
    prompt = drafting_llm.received[0][1]["content"]
    assert "Arabic" in prompt
    assert "firm" in prompt.lower()

    events = client.get(f"/api/audit?action_id={new['id']}").json()["items"]
    revised = next(event for event in events if event["event_type"] == "action_revised")
    assert revised["actor"] == "agent"
    assert revised["details"]["tone"] == "firm"
    assert revised["details"]["language"] == "ar"


def test_redraft_rejects_unsupported_language() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store)

    response = client.post(f"/api/actions/{action_id}/redraft", json={"tone": "friendly", "language": "xx"})

    assert response.status_code == 422


def test_empty_ai_draft_returns_error_and_keeps_original() -> None:
    store = FakeInvoiceStore(DRAFT_ID, "DRAFT")
    client = TestClient(app)
    action_id = propose(client, store)
    app.dependency_overrides[get_llm] = lambda: ScriptedLLM([final_answer("")])

    response = client.post(f"/api/actions/{action_id}/redraft", json={"tone": "friendly", "language": "en"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_error"
    assert client.get(f"/api/actions/{action_id}").json()["approval_status"] == "pending"
