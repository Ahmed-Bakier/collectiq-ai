"""Revising a pending action creates a NEW action version that needs its own approval.

The previous version is superseded, so an approval can never be reused for
changed parameters.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.db.models import ActionRecord
from app.db.types import utc_now
from app.schemas.actions import ApprovalStatus, ExecutionStatus, VerificationStatus
from app.schemas.audit import AuditActor, AuditEventType
from app.services.actions import APPROVAL_WINDOW, get_action, parameters_hash
from app.services.audit import record_event

MAX_MESSAGE_LENGTH = 1000


async def revise_action(
    session: AsyncSession,
    action_id: str,
    *,
    message: str,
    actor: AuditActor,
    details: dict[str, Any] | None = None,
) -> ActionRecord:
    previous = await get_action(session, action_id)  # Also applies expiry.
    if previous.approval_status != ApprovalStatus.PENDING.value:
        raise ConflictError(f"Only pending actions can be edited (current: {previous.approval_status}).")

    text = message.strip()
    if not text or len(text) > MAX_MESSAGE_LENGTH:
        raise ConflictError("The message must be between 1 and 1000 characters.")

    parameters = dict(previous.parameters)
    parameters["note"] = text
    fingerprint = parameters_hash(parameters)
    if fingerprint == previous.parameters_hash:
        raise ConflictError("The message did not change.")

    now = utc_now()
    revised = ActionRecord(
        id=str(uuid.uuid4()),
        run_id=previous.run_id,
        action_type=previous.action_type,
        invoice_id=previous.invoice_id,
        invoice_number=previous.invoice_number,
        client_name=previous.client_name,
        amount=previous.amount,
        currency_code=previous.currency_code,
        reason=previous.reason,
        message_to_client=text,
        parameters=parameters,
        parameters_hash=fingerprint,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        verification_status=VerificationStatus.NOT_VERIFIED.value,
        created_at=now,
        expires_at=now + APPROVAL_WINDOW,
    )
    session.add(revised)
    previous.approval_status = ApprovalStatus.SUPERSEDED.value

    record_event(
        session,
        event_type=AuditEventType.ACTION_SUPERSEDED,
        actor=AuditActor.SYSTEM,
        run_id=previous.run_id,
        action_id=previous.id,
        invoice_id=previous.invoice_id,
        message=f"Replaced by revised version {revised.id}.",
        details={"replaced_by": revised.id},
    )
    who = "User edited" if actor is AuditActor.USER else "Agent redrafted"
    record_event(
        session,
        event_type=AuditEventType.ACTION_REVISED,
        actor=actor,
        run_id=revised.run_id,
        action_id=revised.id,
        invoice_id=revised.invoice_id,
        message=f"{who} the client message for invoice {revised.invoice_number or revised.invoice_id}. "
        "A new approval is required.",
        details={"previous_action_id": previous.id, "parameters_hash": fingerprint, **(details or {})},
    )
    await session.commit()
    return revised
