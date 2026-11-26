"""AI agent API models."""

from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import AnalyzedInvoice


class ProposedActionType(StrEnum):
    SEND_INVOICE = "send_invoice"
    SEND_REMINDER = "send_reminder"


class ProposedAction(BaseModel):
    """An action suggested by the agent. Never executed without user approval."""

    id: str
    action_type: ProposedActionType
    invoice_id: str
    invoice_number: str | None = None
    client_name: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    reason: str
    message_to_client: str | None = None
    parameters: dict[str, Any]  # Exact parameters that would be sent to PayPal.
    requires_approval: bool = True
    status: Literal["awaiting_approval"] = "awaiting_approval"


class ToolCallRecord(BaseModel):
    """User-facing trace of a tool call (no hidden model reasoning)."""

    name: str
    arguments: dict[str, Any]
    status: Literal["ok", "error"]
    detail: str


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AgentRunStatus(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"


class AgentRunResponse(BaseModel):
    run_id: str
    model: str
    summary: str
    status: AgentRunStatus
    requires_approval: bool
    findings: list[AnalyzedInvoice]
    proposed_actions: list[ProposedAction]
    tool_calls: list[ToolCallRecord]
