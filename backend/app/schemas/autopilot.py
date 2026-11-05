"""Collection Autopilot API models."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.actions import ActionResponse, MessageTone


class AutopilotSettingsResponse(BaseModel):
    enabled: bool
    auto_approve_enabled: bool
    auto_approve_max_amount: Decimal
    cooldown_days: int
    max_auto_actions_per_run: int
    schedule_interval_minutes: int
    last_run_at: datetime | None = None


class AutopilotSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    auto_approve_enabled: bool | None = None
    auto_approve_max_amount: Decimal | None = Field(default=None, ge=0, le=10000, decimal_places=2)


class SkippedInvoice(BaseModel):
    invoice_id: str
    invoice_number: str | None = None
    client: str | None = None
    reason: str


class AutopilotProposal(BaseModel):
    action: ActionResponse
    tone: MessageTone
    auto_approved: bool


class AutopilotRunResponse(BaseModel):
    run_id: str
    trigger: str
    summary: str
    evaluated_invoices: int
    eligible_invoices: int
    auto_executed_count: int
    llm_fallback_used: bool
    proposals: list[AutopilotProposal]
    skipped: list[SkippedInvoice]
