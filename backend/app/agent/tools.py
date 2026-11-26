"""Allowlisted agent tools.

Every tool call from the model is validated with Pydantic before execution.
Tools can read data and record proposals; they can never execute PayPal writes.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.message_guard import check_message
from app.db.types import utc_now
from app.integrations.paypal.exceptions import PayPalError
from app.integrations.paypal.invoices import INVOICE_ID_PATTERN
from app.schemas.agent import ProposedAction, ProposedActionType, ToolCallRecord
from app.schemas.analysis import (
    AnalyzedInvoice,
    CollectionState,
    InvoiceAnalysisResponse,
    SuggestedAction,
)
from app.schemas.insights import ClientInsight, InsightsResponse
from app.services.client_insights import ClientInsightsService
from app.services.invoice_analysis import analyze_invoices, collectible_amount
from app.services.invoices import InvoiceService
from app.services.reminders import REMINDER_COOLDOWN

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
    insights: InsightsResponse | None = None
    last_reminders: dict[str, datetime] = field(default_factory=dict)

    async def get_analysis(self) -> InvoiceAnalysisResponse:
        """Load PayPal invoices and analyze them once per run."""
        if self.analysis is None:
            invoices = await self.invoice_service.list_all_invoices()
            self.analysis = analyze_invoices(invoices, today=self.today, timezone=self.timezone)
        return self.analysis

    async def get_insights(self) -> InsightsResponse:
        """Load client payment intelligence once per run (read-only)."""
        if self.insights is None:
            service = ClientInsightsService(self.invoice_service)
            self.insights = await service.build(self.today, self.timezone)
        return self.insights

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

def _compact(item: AnalyzedInvoice, last_reminder: datetime | None = None) -> dict[str, Any]:
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
        "last_reminder_sent_at": last_reminder.isoformat() if last_reminder else None,
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
        "invoices": [_compact(item, context.last_reminders.get(item.invoice.id)) for item in items],
    }


async def _get_invoice_details(context: AgentRunContext, args: InvoiceDetailsArgs) -> dict[str, Any]:
    await context.get_analysis()
    item = context.find(args.invoice_id)
    if item is None:
        return {"error": f"Invoice {args.invoice_id} was not found in PayPal data."}
    return _compact(item, context.last_reminders.get(item.invoice.id))


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

    cooldown_error = _reminder_cooldown_error(context, args)
    if cooldown_error:
        return {"accepted": False, "error": cooldown_error}

    violations = check_message(args.message_to_client)
    if violations:
        return {
            "accepted": False,
            "error": "Message safety check failed: " + "; ".join(violations) + ". Rewrite message_to_client without it.",
        }

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
    if name == "get_client_insights":
        count = len(result.get("clients", []))
        return f"Loaded payment behaviour for {count} client(s)"
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


# ---------- Client payment intelligence (read-only) ----------

class ClientInsightsArgs(StrictArgs):
    client: str | None = Field(default=None, max_length=100)


def _compact_client(insight: ClientInsight) -> dict[str, Any]:
    return {
        "client": insight.client,
        "risk_level": insight.risk_level.value,
        "risk_reasons": insight.risk_reasons,
        "paid_invoices": insight.paid_count,
        "on_time_rate": insight.on_time_rate,
        "avg_days_late": insight.avg_days_late,
        "open_amount": str(insight.open_amount),
        "overdue_amount": str(insight.overdue_amount),
        "currency": insight.currency_code,
    }


async def _get_client_insights(context: AgentRunContext, args: ClientInsightsArgs) -> dict[str, Any]:
    insights = await context.get_insights()
    clients = insights.clients
    if args.client:
        needle = args.client.strip().lower()
        clients = [insight for insight in clients if needle in insight.client.lower()]
        if not clients:
            return {"error": f"No client matching '{args.client}' was found in PayPal data."}

    forecast = insights.forecast
    return {
        "as_of": insights.as_of.isoformat(),
        "clients": [_compact_client(insight) for insight in clients],
        "forecast": {
            "currency": forecast.currency_code,
            "horizon_days": forecast.horizon_days,
            "total_open": str(forecast.total_open),
            "expected_within_horizon": str(forecast.expected_within_horizon),
            "expected_later": str(forecast.expected_later),
            "at_risk_amount": str(forecast.at_risk_amount),
            "weeks": [
                {
                    "period": bucket.label,
                    "expected": str(bucket.expected_amount),
                    "at_risk": str(bucket.at_risk_amount),
                }
                for bucket in forecast.buckets
            ],
            "at_risk_invoices": [
                {
                    "invoice_id": row.invoice_id,
                    "client": row.client,
                    "amount": str(row.amount),
                    "due_date": row.due_date.isoformat(),
                    "expected_date": row.expected_date.isoformat(),
                }
                for row in forecast.invoices
                if row.at_risk
            ],
            "method": forecast.method,
        },
    }


TOOLS["get_client_insights"] = AgentTool("get_client_insights", ClientInsightsArgs, _get_client_insights)
TOOL_DEFINITIONS.append(
    {
        "type": "function",
        "function": {
            "name": "get_client_insights",
            "description": (
                "Read each client's payment behaviour from PayPal payment history (on-time rate, "
                "average days late, risk level with reasons) and the backend's 30-day expected "
                "collections forecast with at-risk invoices. Read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client": {
                        "type": "string",
                        "description": "Optional client name (or part of it) to filter by.",
                    }
                },
                "required": [],
            },
        },
    }
)


# ---------- Reminder cooldown (anti-spam) ----------

def _reminder_cooldown_error(context: AgentRunContext, args: ProposeActionArgs) -> str | None:
    """Reminders for the same invoice must be at least REMINDER_COOLDOWN apart."""
    if args.action_type is not ProposedActionType.SEND_REMINDER:
        return None
    last = context.last_reminders.get(args.invoice_id)
    if last is None or utc_now() - last >= REMINDER_COOLDOWN:
        return None
    return (
        f"A reminder for this invoice was already sent on {last.date().isoformat()}. "
        f"Wait at least {REMINDER_COOLDOWN.days} days between reminders."
    )
