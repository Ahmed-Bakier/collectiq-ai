"""Action approval / execution API models."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ExecutionStatus(StrEnum):
    NOT_STARTED = "not_started"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


class VerificationStatus(StrEnum):
    NOT_VERIFIED = "not_verified"
    VERIFIED = "verified"
    MISMATCH = "mismatch"


class ActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    action_type: str
    invoice_id: str
    invoice_number: str | None = None
    client_name: str | None = None
    amount: str | None = None
    currency_code: str | None = None
    reason: str
    message_to_client: str | None = None
    parameters: dict[str, Any]
    parameters_hash: str
    approval_status: ApprovalStatus
    execution_status: ExecutionStatus
    verification_status: VerificationStatus
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    executed_at: datetime | None = None
    external_reference: str | None = None
    failure_reason: str | None = None


class ActionListResponse(BaseModel):
    items: list[ActionResponse]
