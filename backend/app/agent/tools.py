"""Allowlisted agent tools.

Every tool call from the model is validated with Pydantic before execution.
Tools can read data and record proposals; they can never execute PayPal writes.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.integrations.paypal.exceptions import PayPalError
from app.integrations.paypal.invoices import INVOICE_ID_PATTERN
from app.schemas.agent import ProposedAction, ProposedActionType, ToolCallRecord
from app.schemas.analysis import (
    AnalyzedInvoice,
    CollectionState,
    InvoiceAnalysisResponse,
    SuggestedAction,
)
from app.services.invoice_analysis import analyze_invoices, collectible_amount
from app.services.invoices import InvoiceService

# Which backend suggestion permits which proposal. Anything else is rejected.
ALLOWED_PROPOSALS: dict[SuggestedAction, ProposedActionType] = {
    SuggestedAction.SEND_INVOICE: ProposedActionType.SEND_INVOICE,
    SuggestedAction.SEND_REMINDER: ProposedActionType.SEND_REMINDER,
}
DEFAULT_REMINDER_NOTE = "This is a friendly reminder that this invoice is awaiting payment."


@dataclass
class AgentRunContext:
    """State for a single agent run."""

    invoice_service: InvoiceService
    today: date
    timezone: str
    analysis: InvoiceAnalysisResponse | None = None
    proposals: list[ProposedAction] = field(default_factory=list)
    tool_records: list[ToolCallRecord] = field(default_factory=list)

    async def get_analysis(self) -> InvoiceAnalysisResponse:
        """Load PayPal invoices and analyze them once per run."""
        if self.analysis is None:
            invoices = await self.invoice_service.list_all_invoices()
            self.analysis = analyze_invoices(invoices, today=self.today, timezone=self.timezone)
        return self.analysis

    def find(self, invoice_id: str) -> AnalyzedInvoice | None:
        if self.analysis is None:
            return None
        return next((item for item in self.analysis.invoices if item.invoice.id == invoice_id), None)


# ---------- Argument models ----------

class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisArgs(StrictArgs):
    include_closed: bool = False


class InvoiceDetailsArgs(StrictArgs):
    invoice_id: str = Field(pattern=INVOICE_ID_PATTERN.pattern)


class ProposeActionArgs(StrictArgs):
    invoice_id: str = Field(pattern=INVOICE_ID_PATTERN.pattern)
    action_type: ProposedActionType
    reason: str = Field(min_length=1, max_length=500)
    message_to_client: str | None = Field(default=None, max_length=1000)


# ---------- Tool handlers ----------

def _compact(item: AnalyzedInvoice) -> dict[str, Any]:
    invoice = item.invoice
    amount = collectible_amount(invoice)
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "client": invoice.recipient_business_name or invoice.recipient_name,
        "contact_name": invoice.recipient_name,
        "paypal_status": invoice.status,
        "collection_state": item.collection_state.value,
        "amount_owed": str(amount) if amount is not None else None,
        "currency": invoice.currency_code,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "days_overdue": item.days_overdue,
        "days_until_due": item.days_until_due,
        "priority_score": item.priority_score,
        "priority_level": item.priority_level.value,
        "suggested_action": item.suggested_action.value,
        "reasons": item.reasons,
    }


async def _get_invoice_analysis(context: AgentRunContext, args: AnalysisArgs) -> dict[str, Any]:
    analysis = await context.get_analysis()
    items = [
        item
        for item in analysis.invoices
        if args.include_closed or item.collection_state is not CollectionState.CLOSED
    ]
    return {
        "as_of": analysis.as_of.isoformat(),
        "timezone": analysis.timezone,
        "summary": analysis.summary.model_dump(mode="json"),
        "invoices": [_compact(item) for item in items],
    }


async def _get_invoice_details(context: AgentRunContext, args: InvoiceDetailsArgs) -> dict[str, Any]:
    await context.get_analysis()
    item = context.find(args.invoice_id)
    if item is None:
        return {"error": f"Invoice {args.invoice_id} was not found in PayPal data."}
    return _compact(item)


def _build_proposal(item: AnalyzedInvoice, args: ProposeActionArgs) -> ProposedAction:
    invoice = item.invoice
    message = args.message_to_client.strip() if args.message_to_client else None

    if args.action_type is ProposedActionType.SEND_INVOICE:
        parameters: dict[str, Any] = {
            "invoice_id": invoice.id,
            "send_to_recipient": True,
            "send_to_invoicer": False,
        }
        if message:
            parameters["note"] = message
    else:
        parameters = {
            "invoice_id": invoice.id,
            "subject": f"Payment reminder: invoice {invoice.invoice_number or invoice.id}",
            "note": message or DEFAULT_REMINDER_NOTE,
        }

    return ProposedAction(
        id=str(uuid.uuid4()),
        action_type=args.action_type,
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        client_name=invoice.recipient_business_name or invoice.recipient_name,
        amount=collectible_amount(invoice),
        currency_code=invoice.currency_code,
        reason=args.reason.strip(),
        message_to_client=message,
        parameters=parameters,
    )


async def _propose_action(context: AgentRunContext, args: ProposeActionArgs) -> dict[str, Any]:
    await context.get_analysis()
    item = context.find(args.invoice_id)
    if item is None:
        return {"accepted": False, "error": f"Invoice {args.invoice_id} was not found in PayPal data."}

    allowed = ALLOWED_PROPOSALS.get(item.suggested_action)
    if allowed is not args.action_type:
        return {
            "accepted": False,
            "error": (
                f"Action '{args.action_type.value}' is not allowed for invoice {args.invoice_id}. "
                f"The backend allows: '{item.suggested_action.value}'."
            ),
        }

    duplicate = any(
        proposal.invoice_id == args.invoice_id and proposal.action_type is args.action_type
        for proposal in context.proposals
    )
    if duplicate:
        return {"accepted": False, "error": "This action was already proposed in this run."}

    proposal = _build_proposal(item, args)
    context.proposals.append(proposal)
    return {
        "accepted": True,
        "action_id": proposal.id,
        "status": "awaiting_user_approval",
        "note": "Not executed. The user must approve this action in the app.",
    }


# ---------- Registry ----------

@dataclass(frozen=True)
class AgentTool:
    name: str
    args_model: type[BaseModel]
    handler: Callable[[AgentRunContext, Any], Awaitable[dict[str, Any]]]


TOOLS: dict[str, AgentTool] = {
    "get_invoice_analysis": AgentTool("get_invoice_analysis", AnalysisArgs, _get_invoice_analysis),
    "get_invoice_details": AgentTool("get_invoice_details", InvoiceDetailsArgs, _get_invoice_details),
    "propose_action": AgentTool("propose_action", ProposeActionArgs, _propose_action),
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_invoice_analysis",
            "description": (
                "Fetch all invoices from PayPal with the backend's deterministic collection analysis: "
                "summary totals and, for each invoice, its state, days overdue, priority and the "
                "single action the backend allows (suggested_action)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "include_closed": {
                        "type": "boolean",
                        "description": "Include paid or cancelled invoices. Default false.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_invoice_details",
            "description": "Return the analysis for one invoice by its PayPal invoice ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "string",
                        "description": "PayPal invoice ID, e.g. INV2-XXXX-XXXX-XXXX-XXXX.",
                    }
                },
                "required": ["invoice_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_action",
            "description": (
                "Propose ONE action for the user to approve. Only allowed when action_type matches "
                "the invoice's suggested_action. This does NOT execute anything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string", "description": "PayPal invoice ID."},
                    "action_type": {"type": "string", "enum": ["send_invoice", "send_reminder"]},
                    "reason": {
                        "type": "string",
                        "description": "Short factual reason based on the analysis (max 500 characters).",
                    },
                    "message_to_client": {
                        "type": "string",
                        "description": "Short, polite message to the client (max 3 sentences).",
                    },
                },
                "required": ["invoice_id", "action_type", "reason"],
            },
        },
    },
]


# ---------- Execution ----------

def _describe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'arguments'}: {error['msg']}"
            for error in exc.errors()[:3]
        )
    return str(exc)[:200]


def _describe_success(name: str, result: dict[str, Any]) -> str:
    if name == "get_invoice_analysis":
        return f"Analyzed {len(result.get('invoices', []))} invoices from PayPal"
    if name == "get_invoice_details":
        return f"Loaded invoice {result.get('invoice_id')}"
    if name == "propose_action":
        return f"Proposed action {result.get('action_id')} (awaiting approval)"
    return "ok"


def _record(
    context: AgentRunContext,
    name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    error = result.get("error")
    context.tool_records.append(
        ToolCallRecord(
            name=name,
            arguments=arguments,
            status="error" if error else "ok",
            detail=str(error) if error else _describe_success(name, result),
        )
    )
    return result


async def execute_tool(context: AgentRunContext, name: str, raw_arguments: str) -> dict[str, Any]:
    """Validate and run one tool call. Never raises for model mistakes."""
    tool = TOOLS.get(name)
    if tool is None:
        return _record(context, name, {}, {"error": f"Unknown tool '{name}'. Allowed: {', '.join(TOOLS)}."})

    try:
        parsed = json.loads(raw_arguments or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("Arguments must be a JSON object.")
        args = tool.args_model.model_validate(parsed)
    except ValueError as exc:  # Includes JSON errors and Pydantic ValidationError.
        return _record(context, name, {}, {"error": f"Invalid arguments: {_describe_error(exc)}"})

    try:
        result = await tool.handler(context, args)
    except PayPalError:
        result = {"error": "PayPal data is temporarily unavailable."}

    return _record(context, name, args.model_dump(mode="json"), result)


# Public alias used by the autopilot playbook.
build_proposal = _build_proposal
