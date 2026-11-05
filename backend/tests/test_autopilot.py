"""Tests for the Collection Autopilot (fake LLM, stateful fake PayPal, temp DB)."""

from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from app.agent.dependencies import get_optional_llm
from app.agent.llm import LLM
from app.api.dependencies import get_today
from app.integrations.paypal.dependencies import get_paypal_client
from app.main import app
from tests.agent_fakes import ScriptedLLM, final_answer
from tests.paypal_state_fake import FakeInvoiceBook, invoice_json

TODAY = date(2026, 11, 20)
SMALL_OVERDUE = "INV2-SMAL-0001"  # 250 USD, 3 days overdue  -> friendly reminder
LARGE_OVERDUE = "INV2-LARG-0001"  # 900 USD, 15 days overdue -> firm reminder
DRAFT = "INV2-DRFT-0001"          # 300 USD draft            -> send invoice
NOT_DUE = "INV2-LATR-0001"        # due in 10 days           -> no action


def make_book() -> FakeInvoiceBook:
    return FakeInvoiceBook(
        [
            invoice_json(SMALL_OVERDUE, "SENT", "2026-11-17", "250.00", "Small Co"),
            invoice_json(LARGE_OVERDUE, "SENT", "2026-11-05", "900.00", "Large Co"),
            invoice_json(DRAFT, "DRAFT", "2026-11-30", "300.00", "Draft Co"),
            invoice_json(NOT_DUE, "SENT", "2026-11-30", "400.00", "Later Co"),
        ]
    )


def drafting_llm(count: int = 3) -> ScriptedLLM:
    return ScriptedLLM([final_answer(f"AI drafted message {index}") for index in range(count)])


def setup(book: FakeInvoiceBook, llm: LLM | None) -> TestClient:
    app.dependency_overrides[get_paypal_client] = book.client
    app.dependency_overrides[get_optional_llm] = lambda: llm
    app.dependency_overrides[get_today] = lambda: TODAY
    return TestClient(app)


def by_invoice(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {proposal["action"]["invoice_id"]: proposal for proposal in run["proposals"]}


def test_run_applies_playbook_and_waits_for_approval() -> None:
    book = make_book()
    client = setup(book, drafting_llm())

    run = client.post("/api/autopilot/run").json()
    proposals = by_invoice(run)

    assert set(proposals) == {SMALL_OVERDUE, LARGE_OVERDUE, DRAFT}
    assert proposals[SMALL_OVERDUE]["tone"] == "friendly"
    assert proposals[LARGE_OVERDUE]["tone"] == "firm"
    assert proposals[DRAFT]["action"]["action_type"] == "send_invoice"
    assert all(proposal["action"]["approval_status"] == "pending" for proposal in run["proposals"])
    assert proposals[SMALL_OVERDUE]["action"]["message_to_client"].startswith("AI drafted message")
    assert run["evaluated_invoices"] == 4
    assert run["auto_executed_count"] == 0
    assert run["llm_fallback_used"] is False
    assert book.writes == []


def test_templates_are_used_when_llm_is_unavailable() -> None:
    client = setup(make_book(), None)

    run = client.post("/api/autopilot/run").json()

    assert run["llm_fallback_used"] is True
    message = by_invoice(run)[LARGE_OVERDUE]["action"]["message_to_client"]
    assert "15 days overdue" in message


def test_policy_auto_executes_only_small_friendly_reminders() -> None:
    book = make_book()
    client = setup(book, drafting_llm())
    client.put("/api/autopilot/settings", json={"auto_approve_enabled": True, "auto_approve_max_amount": "500"})

    run = client.post("/api/autopilot/run").json()
    proposals = by_invoice(run)

    small = proposals[SMALL_OVERDUE]
    assert small["auto_approved"] is True
    assert small["action"]["execution_status"] == "succeeded"
    assert small["action"]["verification_status"] == "verified"
    assert proposals[LARGE_OVERDUE]["auto_approved"] is False  # Firm tone needs a human.
    assert proposals[DRAFT]["auto_approved"] is False  # Invoices are never auto-sent.
    assert [write.url.path.split("/")[-2] for write in book.writes] == [SMALL_OVERDUE]

    events = client.get(f"/api/audit?action_id={small['action']['id']}").json()["items"]
    approval = next(event for event in events if event["event_type"] == "action_approved")
    assert approval["actor"] == "system"
    assert "policy" in approval["message"].lower()


def test_kill_switch_blocks_runs() -> None:
    book = make_book()
    client = setup(book, drafting_llm())
    client.put("/api/autopilot/settings", json={"enabled": False})

    response = client.post("/api/autopilot/run")

    assert response.status_code == 409
    assert book.writes == []
    assert client.get("/api/autopilot/settings").json()["enabled"] is False


def test_second_run_skips_pending_and_cooldown() -> None:
    book = make_book()
    client = setup(book, drafting_llm())
    client.put("/api/autopilot/settings", json={"auto_approve_enabled": True, "auto_approve_max_amount": "500"})
    client.post("/api/autopilot/run")

    second = client.post("/api/autopilot/run").json()

    assert second["proposals"] == []
    reasons = {skip["invoice_id"]: skip["reason"] for skip in second["skipped"]}
    assert "awaiting approval" in reasons[LARGE_OVERDUE]
    assert "awaiting approval" in reasons[DRAFT]
    assert "reminder was sent" in reasons[SMALL_OVERDUE]


def test_settings_validation() -> None:
    client = setup(make_book(), None)

    assert client.put("/api/autopilot/settings", json={"auto_approve_max_amount": "-5"}).status_code == 422
    assert client.put("/api/autopilot/settings", json={"unknown": True}).status_code == 422


def test_autopilot_run_events_are_authored_by_system() -> None:
    client = setup(make_book(), drafting_llm())

    run = client.post("/api/autopilot/run").json()

    events = client.get("/api/audit?limit=200").json()["items"]
    actors = {event["event_type"]: event["actor"] for event in events if event["run_id"] == run["run_id"]}
    assert actors["action_proposed"] == "system"
    assert actors["agent_run_completed"] == "system"
