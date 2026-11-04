"""Audit trail API models."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditActor(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class AuditEventType(StrEnum):
    AGENT_RUN_REQUESTED = "agent_run_requested"
    AGENT_TOOL_CALL = "agent_tool_call"
    ACTION_PROPOSED = "action_proposed"
    ACTION_SUPERSEDED = "action_superseded"
    ACTION_EXPIRED = "action_expired"
    AGENT_RUN_COMPLETED = "agent_run_completed"


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    event_type: str
    actor: str
    run_id: str | None = None
    action_id: str | None = None
    invoice_id: str | None = None
    message: str
    details: dict[str, Any]


class AuditListResponse(BaseModel):
    items: list[AuditEventResponse]
