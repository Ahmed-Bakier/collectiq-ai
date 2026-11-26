"""Safety report: live evidence from the append-only audit trail."""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.message_guard import RULES
from app.db.models import AuditEventRecord
from app.db.types import utc_now
from app.schemas.audit import AuditActor, AuditEventType
from app.schemas.safety import Guardrail, SafetyCounts, SafetyReport

GUARD_FAILURE_PREFIX = "Message safety check failed"

GUARDRAILS: tuple[Guardrail, ...] = (
    Guardrail(name="PayPal Sandbox only", description="Live PayPal mode is rejected by configuration."),
    Guardrail(
        name="Allowlisted, validated tools",
        description="The AI can only read data and propose actions; unknown tools and invalid arguments are rejected.",
    ),
    Guardrail(
        name="Deterministic eligibility",
        description="The backend decides which action each invoice allows; the AI cannot override it.",
    ),
    Guardrail(
        name="Message safety check",
        description="Every AI-written message is scanned for payment redirection, links, threats, "
        "invented charges and injected instructions before anyone sees it.",
    ),
    Guardrail(
        name="Data, not instructions",
        description="PayPal data reaches the AI only inside tool results, marked as data to never follow.",
    ),
    Guardrail(
        name="Hash-bound human approval",
        description="Approval is tied to a SHA-256 hash of the exact parameters; any edit needs a new approval.",
    ),
    Guardrail(
        name="Execute once, verify in PayPal",
        description="Each action runs once with a PayPal-Request-Id, is re-checked before and verified after; "
        "unknown outcomes are never retried.",
    ),
    Guardrail(
        name="Strict autopilot policy",
        description="Auto-approval is off by default, limited to small friendly reminders, never invoices or "
        "high-risk clients, with a kill switch.",
    ),
    Guardrail(name="Append-only audit trail", description="Every request, tool call, decision and result is recorded."),
)


async def build_safety_report(session: AsyncSession) -> SafetyReport:
    rows = (
        await session.execute(
            select(
                AuditEventRecord.event_type,
                AuditEventRecord.actor,
                AuditEventRecord.action_id,
                AuditEventRecord.message,
                AuditEventRecord.details,
            )
        )
    ).all()

    counts: Counter[str] = Counter()
    approved_actions: set[str] = set()
    started_actions: set[str] = set()

    for event_type, actor, action_id, message, details in rows:
        counts[event_type] += 1
        if event_type == AuditEventType.AGENT_RUN_REQUESTED.value and actor == AuditActor.USER.value:
            counts["user_runs"] += 1
        elif event_type == AuditEventType.AGENT_TOOL_CALL.value and (details or {}).get("status") == "error":
            counts["tool_errors"] += 1
            if (message or "").find(GUARD_FAILURE_PREFIX) != -1:
                counts["guard_tool_errors"] += 1
        elif event_type == AuditEventType.ACTION_APPROVED.value:
            counts["policy_approvals" if actor == AuditActor.SYSTEM.value else "user_approvals"] += 1
            if action_id:
                approved_actions.add(action_id)
        elif event_type == AuditEventType.EXECUTION_STARTED.value and action_id:
            started_actions.add(action_id)

    return SafetyReport(
        generated_at=utc_now(),
        counts=SafetyCounts(
            agent_runs=counts["user_runs"],
            autopilot_runs=counts[AuditEventType.AUTOPILOT_RUN_COMPLETED.value],
            tool_calls=counts[AuditEventType.AGENT_TOOL_CALL.value],
            tool_calls_rejected=counts["tool_errors"],
            ai_messages_blocked=counts[AuditEventType.AI_OUTPUT_BLOCKED.value] + counts["guard_tool_errors"],
            proposals=counts[AuditEventType.ACTION_PROPOSED.value],
            approved_by_user=counts["user_approvals"],
            approved_by_policy=counts["policy_approvals"],
            rejected_by_user=counts[AuditEventType.ACTION_REJECTED.value],
            executions_succeeded=counts[AuditEventType.EXECUTION_SUCCEEDED.value],
            executions_blocked=counts[AuditEventType.EXECUTION_BLOCKED.value],
            verified_in_paypal=counts[AuditEventType.VERIFICATION_COMPLETED.value],
            executions_without_approval=len(started_actions - approved_actions),
        ),
        guardrails=list(GUARDRAILS),
        message_rules=[rule.description for rule in RULES],
    )
