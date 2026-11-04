"""Tests for the collection agent loop and tool guardrails (fake LLM, mocked PayPal)."""

import asyncio
from datetime import date

import httpx

from app.agent.agent import MAX_AGENT_STEPS, CollectionAgent
from app.agent.llm import LLM
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.schemas.agent import AgentRunResponse, AgentRunStatus, ProposedActionType
from app.services.invoices import InvoiceService
from tests.agent_fakes import LoopingLLM, ScriptedLLM, final_answer, tool_call
from tests.fakes import make_paypal_client, sample_paypal_invoice

TODAY = date(2026, 11, 20)
OVERDUE_ID = "INV2-TEST-AAAA-BBBB-CCCC"  # Sample invoice: UNPAID, due 2026-11-15.
DRAFT_ID = "INV2-DRAFT-0001"


def make_service() -> InvoiceService:
    invoices = [sample_paypal_invoice(), sample_paypal_invoice(id=DRAFT_ID, status="DRAFT")]
    client = make_paypal_client(
        lambda request: httpx.Response(200, json={"items": invoices, "total_items": 2, "total_pages": 1})
    )
    return InvoiceService(PayPalInvoicesAPI(client))


def run_agent(llm: LLM, message: str = "Which invoices need attention?") -> AgentRunResponse:
    agent = CollectionAgent(llm, make_service(), today=TODAY, timezone="America/Los_Angeles")
    return asyncio.run(agent.run(message))


def test_agent_reads_analysis_then_summarizes() -> None:
    llm = ScriptedLLM([tool_call("get_invoice_analysis", {}), final_answer("One invoice is overdue.")])
    result = run_agent(llm)

    assert result.summary == "One invoice is overdue."
    assert result.status is AgentRunStatus.COMPLETED
    assert result.requires_approval is False
    assert [call.name for call in result.tool_calls] == ["get_invoice_analysis"]
    assert result.tool_calls[0].status == "ok"
    assert {item.invoice.id for item in result.findings} == {OVERDUE_ID, DRAFT_ID}

    tool_messages = [message for message in llm.received[1] if message["role"] == "tool"]
    assert OVERDUE_ID in tool_messages[0]["content"]


def test_eligible_proposal_awaits_approval() -> None:
    llm = ScriptedLLM(
        [
            tool_call("get_invoice_analysis", {}),
            tool_call(
                "propose_action",
                {
                    "invoice_id": OVERDUE_ID,
                    "action_type": "send_reminder",
                    "reason": "Overdue by 5 days",
                    "message_to_client": "Hi Jane, a friendly reminder about this invoice.",
                },
                call_id="call_2",
            ),
            final_answer("I proposed a reminder."),
        ]
    )
    result = run_agent(llm)

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.requires_approval is True
    action = result.proposed_actions[0]
    assert action.action_type is ProposedActionType.SEND_REMINDER
    assert action.invoice_id == OVERDUE_ID
    assert action.parameters["note"] == "Hi Jane, a friendly reminder about this invoice."
    assert action.status == "awaiting_approval"


def test_ineligible_action_is_rejected_by_backend() -> None:
    llm = ScriptedLLM(
        [
            tool_call("propose_action", {"invoice_id": DRAFT_ID, "action_type": "send_reminder", "reason": "x"}),
            final_answer("done"),
        ]
    )
    result = run_agent(llm)

    assert result.proposed_actions == []
    assert result.tool_calls[0].status == "error"
    assert "not allowed" in result.tool_calls[0].detail


def test_unknown_tool_is_blocked() -> None:
    llm = ScriptedLLM([tool_call("delete_all_invoices", {}), final_answer("ok")])
    result = run_agent(llm)

    assert result.tool_calls[0].status == "error"
    assert "Unknown tool" in result.tool_calls[0].detail


def test_invalid_json_arguments_are_rejected() -> None:
    llm = ScriptedLLM([tool_call("get_invoice_details", "{not json"), final_answer("ok")])
    result = run_agent(llm)

    assert result.tool_calls[0].status == "error"
    assert "Invalid arguments" in result.tool_calls[0].detail


def test_malicious_invoice_id_is_rejected() -> None:
    llm = ScriptedLLM(
        [tool_call("get_invoice_details", {"invoice_id": "../../v1/oauth2/token"}), final_answer("ok")]
    )
    result = run_agent(llm)

    assert result.tool_calls[0].status == "error"


def test_duplicate_proposal_is_rejected() -> None:
    args = {"invoice_id": DRAFT_ID, "action_type": "send_invoice", "reason": "Draft not sent yet"}
    llm = ScriptedLLM(
        [
            tool_call("propose_action", args),
            tool_call("propose_action", args, call_id="call_2"),
            final_answer("done"),
        ]
    )
    result = run_agent(llm)

    assert len(result.proposed_actions) == 1
    assert result.tool_calls[1].status == "error"
    assert "already proposed" in result.tool_calls[1].detail


def test_agent_stops_after_max_steps() -> None:
    result = run_agent(LoopingLLM())

    assert result.status is AgentRunStatus.INCOMPLETE
    assert len(result.tool_calls) == MAX_AGENT_STEPS
