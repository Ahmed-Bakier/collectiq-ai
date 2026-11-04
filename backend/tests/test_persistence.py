"""Tests for persisted agent runs, proposed actions and the audit trail."""

import asyncio
from datetime import date, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.dependencies import get_llm
from app.api.dependencies import get_today
from app.db.models import ActionRecord, AgentRunRecord
from app.db.types import utc_now
from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from app.services.actions import parameters_hash
from tests.agent_fakes import ScriptedLLM, final_answer, tool_call
from tests.fakes import make_paypal_client, sample_paypal_invoice

DRAFT_ID = "INV2-DRAFT-0001"
EXPIRED_ACTION_ID = "11111111-1111-1111-1111-111111111111"


def use_fakes(llm: ScriptedLLM) -> None:
    invoices = [sample_paypal_invoice(id=DRAFT_ID, status="DRAFT")]
    client = make_paypal_client(
        lambda request: httpx.Response(200, json={"items": invoices, "total_items": 1, "total_pages": 1})
    )
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_paypal_client] = lambda: client
    app.dependency_overrides[get_today] = lambda: date(2026, 11, 20)


def proposing_llm() -> ScriptedLLM:
    return ScriptedLLM(
        [
            tool_call("get_invoice_analysis", {}),
            tool_call(
                "propose_action",
                {"invoice_id": DRAFT_ID, "action_type": "send_invoice", "reason": "Draft not sent"},
                call_id="call_2",
            ),
            final_answer("Proposed sending the draft."),
        ]
    )


def test_agent_run_persists_action_and_audit_trail() -> None:
    use_fakes(proposing_llm())
    client = TestClient(app)

    run = client.post("/api/agent/runs", json={"message": "Check my invoices"}).json()
    action_id = run["proposed_actions"][0]["id"]

    actions = client.get("/api/actions").json()["items"]
    assert [action["id"] for action in actions] == [action_id]
    action = actions[0]
    assert action["run_id"] == run["run_id"]
    assert action["approval_status"] == "pending"
    assert action["execution_status"] == "not_started"
    assert action["verification_status"] == "not_verified"
    assert action["parameters"]["invoice_id"] == DRAFT_ID
    assert action["parameters_hash"] == parameters_hash(action["parameters"])

    events = client.get("/api/audit").json()["items"]
    assert [event["event_type"] for event in events] == [
        "agent_run_completed",
        "action_proposed",
        "agent_tool_call",
        "agent_tool_call",
        "agent_run_requested",
    ]
    assert events[-1]["actor"] == "user"


def test_new_proposal_supersedes_pending_duplicate() -> None:
    client = TestClient(app)
    use_fakes(proposing_llm())
    first = client.post("/api/agent/runs", json={"message": "first"}).json()
    use_fakes(proposing_llm())
    second = client.post("/api/agent/runs", json={"message": "second"}).json()

    statuses = {item["id"]: item["approval_status"] for item in client.get("/api/actions").json()["items"]}
    assert statuses[first["proposed_actions"][0]["id"]] == "superseded"
    assert statuses[second["proposed_actions"][0]["id"]] == "pending"


def test_filter_actions_by_approval_status() -> None:
    use_fakes(proposing_llm())
    client = TestClient(app)
    client.post("/api/agent/runs", json={"message": "Check my invoices"})

    assert len(client.get("/api/actions?approval_status=pending").json()["items"]) == 1
    assert client.get("/api/actions?approval_status=approved").json()["items"] == []


def test_unknown_action_returns_404() -> None:
    response = TestClient(app).get("/api/actions/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_expired_action_is_marked_on_read(db_sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async def insert_expired_action() -> None:
        now = utc_now()
        async with db_sessionmaker() as session:
            session.add(AgentRunRecord(id="run-1", user_message="x", summary="x", status="awaiting_approval", model="m"))
            session.add(
                ActionRecord(
                    id=EXPIRED_ACTION_ID,
                    run_id="run-1",
                    action_type="send_invoice",
                    invoice_id=DRAFT_ID,
                    reason="x",
                    parameters={"invoice_id": DRAFT_ID},
                    parameters_hash="h",
                    created_at=now - timedelta(days=2),
                    expires_at=now - timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(insert_expired_action())
    client = TestClient(app)

    assert client.get(f"/api/actions/{EXPIRED_ACTION_ID}").json()["approval_status"] == "expired"
    assert client.get("/api/audit").json()["items"][0]["event_type"] == "action_expired"


def test_parameters_hash_ignores_key_order() -> None:
    assert parameters_hash({"a": 1, "b": 2}) == parameters_hash({"b": 2, "a": 1})
    assert parameters_hash({"a": 1}) != parameters_hash({"a": 2})
