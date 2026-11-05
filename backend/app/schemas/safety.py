"""Safety report API models."""

from datetime import datetime

from pydantic import BaseModel


class Guardrail(BaseModel):
    name: str
    description: str


class SafetyCounts(BaseModel):
    agent_runs: int
    autopilot_runs: int
    tool_calls: int
    tool_calls_rejected: int
    ai_messages_blocked: int
    proposals: int
    approved_by_user: int
    approved_by_policy: int
    rejected_by_user: int
    executions_succeeded: int
    executions_blocked: int
    verified_in_paypal: int
    executions_without_approval: int  # Must always be 0.


class SafetyReport(BaseModel):
    generated_at: datetime
    counts: SafetyCounts
    guardrails: list[Guardrail]
    message_rules: list[str]
