"""Persistence of agent runs and proposed actions (approval lifecycle part 1)."""

import hashlib
import json
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models import ActionRecord, AgentRunRecord
from app.db.types import utc_now
from app.schemas.actions import ApprovalStatus
from app.schemas.agent import AgentRunResponse, ProposedAction
from app.schemas.audit import AuditActor, AuditEventType
from app.services.audit import record_event

APPROVAL_WINDOW = timedelta(hours=24)


def parameters_hash(parameters: dict[str, Any]) -> str:
    """Stable fingerprint of action parameters (key order does not matter)."""
    canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _supersede_pending_duplicates(session: AsyncSession, proposal: ProposedAction) -> None:
    """Only one pending action may exist per invoice and action type."""
    result = await session.execute(
        select(ActionRecord).where(
            ActionRecord.invoice_id == proposal.invoice_id,
            ActionRecord.action_type == proposal.action_type.value,
            ActionRecord.approval_status == ApprovalStatus.PENDING.value,
        )
    )
    for old in result.scalars():
        old.approval_status = ApprovalStatus.SUPERSEDED.value
        record_event(
            session,
            event_type=AuditEventType.ACTION_SUPERSEDED,
            actor=AuditActor.SYSTEM,
            run_id=old.run_id,
            action_id=old.id,
            invoice_id=old.invoice_id,
            message=f"Replaced by a newer proposal ({proposal.id}).",
            details={"replaced_by": proposal.id},
        )


async def save_agent_run(
    session: AsyncSession,
    user_message: str,
    result: AgentRunResponse,
    requested_by: AuditActor = AuditActor.USER,
) -> None:
    """Persist an agent run, its proposed actions and the audit trail."""
    now = utc_now()
    session.add(
        AgentRunRecord(
            id=result.run_id,
            user_message=user_message,
            summary=result.summary,
            status=result.status.value,
            model=result.model,
            tool_calls=[call.model_dump(mode="json") for call in result.tool_calls],
            created_at=now,
        )
    )
    record_event(
        session,
        event_type=AuditEventType.AGENT_RUN_REQUESTED,
        actor=requested_by,
        run_id=result.run_id,
        message=f"Request ({requested_by.value}): {user_message[:200]}",
    )

    for call in result.tool_calls:
        record_event(
            session,
            event_type=AuditEventType.AGENT_TOOL_CALL,
            actor=AuditActor.AGENT,
            run_id=result.run_id,
            message=f"{call.name} ({call.status}): {call.detail}",
            details={"tool": call.name, "status": call.status, "arguments": call.arguments},
        )

    for proposal in result.proposed_actions:
        await _supersede_pending_duplicates(session, proposal)
        fingerprint = parameters_hash(proposal.parameters)
        session.add(
            ActionRecord(
                id=proposal.id,
                run_id=result.run_id,
                action_type=proposal.action_type.value,
                invoice_id=proposal.invoice_id,
                invoice_number=proposal.invoice_number,
                client_name=proposal.client_name,
                amount=str(proposal.amount) if proposal.amount is not None else None,
                currency_code=proposal.currency_code,
                reason=proposal.reason,
                message_to_client=proposal.message_to_client,
                parameters=proposal.parameters,
                parameters_hash=fingerprint,
                created_at=now,
                expires_at=now + APPROVAL_WINDOW,
            )
        )
        record_event(
            session,
            event_type=AuditEventType.ACTION_PROPOSED,
            actor=AuditActor.AGENT,
            run_id=result.run_id,
            action_id=proposal.id,
            invoice_id=proposal.invoice_id,
            message=f"Proposed {proposal.action_type.value} for invoice {proposal.invoice_number or proposal.invoice_id}.",
            details={"parameters_hash": fingerprint, "reason": proposal.reason},
        )

    record_event(
        session,
        event_type=AuditEventType.AGENT_RUN_COMPLETED,
        actor=AuditActor.AGENT,
        run_id=result.run_id,
        message=f"Agent run finished with status '{result.status.value}' "
        f"({len(result.proposed_actions)} action(s) awaiting approval).",
        details={
            "model": result.model,
            "tool_calls": len(result.tool_calls),
            "proposed_actions": len(result.proposed_actions),
        },
    )
    await session.commit()


async def _expire_stale(session: AsyncSession, actions: Sequence[ActionRecord]) -> bool:
    """Mark pending actions whose approval window passed as expired."""
    now = utc_now()
    changed = False
    for action in actions:
        if action.approval_status == ApprovalStatus.PENDING.value and action.expires_at <= now:
            action.approval_status = ApprovalStatus.EXPIRED.value
            record_event(
                session,
                event_type=AuditEventType.ACTION_EXPIRED,
                actor=AuditActor.SYSTEM,
                run_id=action.run_id,
                action_id=action.id,
                invoice_id=action.invoice_id,
                message="Approval window expired; the action can no longer be approved.",
            )
            changed = True
    return changed


async def list_actions(
    session: AsyncSession,
    *,
    approval_status: ApprovalStatus | None = None,
    limit: int = 50,
) -> list[ActionRecord]:
    query = select(ActionRecord).order_by(ActionRecord.created_at.desc(), ActionRecord.id).limit(limit)
    if approval_status is not None:
        query = query.where(ActionRecord.approval_status == approval_status.value)
    actions = list((await session.execute(query)).scalars())

    if await _expire_stale(session, actions):
        await session.commit()
    if approval_status is not None:
        actions = [action for action in actions if action.approval_status == approval_status.value]
    return actions


async def get_action(session: AsyncSession, action_id: str) -> ActionRecord:
    action = await session.get(ActionRecord, action_id)
    if action is None:
        raise NotFoundError(f"Action {action_id} was not found.")
    if await _expire_stale(session, [action]):
        await session.commit()
    return action
