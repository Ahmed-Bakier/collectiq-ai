"""Approval and execution engine (backend-enforced).

Rules:
- Only pending, unexpired actions can be approved or rejected.
- Approval binds to the exact parameters hash the user reviewed.
- Execution requires approval, an unchanged hash, a fresh approval and happens at most once.
- PayPal is read before execution (precondition) and after it (verification).
- Ambiguous write outcomes are recorded and never retried automatically.
"""

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.db.models import ActionRecord
from app.db.types import utc_now
from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalConnectionError,
    PayPalError,
    PayPalWriteOutcomeUnknownError,
)
from app.integrations.paypal.invoices import INVOICE_ID_PATTERN, PayPalInvoicesAPI
from app.schemas.actions import ApprovalStatus, ExecutionStatus, VerificationStatus
from app.schemas.agent import ProposedActionType
from app.schemas.audit import AuditActor, AuditEventType
from app.services.actions import get_action, parameters_hash
from app.services.audit import record_event

EXECUTION_WINDOW = timedelta(minutes=15)

COLLECTIBLE = frozenset({"SENT", "UNPAID", "PARTIALLY_PAID", "SHARED"})

# PayPal status required BEFORE executing each action type.
PRECONDITION_STATUSES: dict[ProposedActionType, frozenset[str]] = {
    ProposedActionType.SEND_INVOICE: frozenset({"DRAFT"}),
    ProposedActionType.SEND_REMINDER: COLLECTIBLE,
}

# PayPal status that confirms the result AFTER executing each action type.
# A reminder does not change the status; PayPal's 2xx plus an open invoice is the evidence.
VERIFIED_STATUSES: dict[ProposedActionType, frozenset[str]] = {
    ProposedActionType.SEND_INVOICE: frozenset({"SENT", "UNPAID", "SCHEDULED", "SHARED"}),
    ProposedActionType.SEND_REMINDER: COLLECTIBLE,
}


class SendInvoiceParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str = Field(pattern=INVOICE_ID_PATTERN.pattern)
    send_to_recipient: bool = True
    send_to_invoicer: bool = False
    subject: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class SendReminderParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str = Field(pattern=INVOICE_ID_PATTERN.pattern)
    subject: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


PARAMETER_MODELS: dict[ProposedActionType, type[BaseModel]] = {
    ProposedActionType.SEND_INVOICE: SendInvoiceParameters,
    ProposedActionType.SEND_REMINDER: SendReminderParameters,
}


def _audit(session: AsyncSession, action: ActionRecord, event_type: AuditEventType, actor: AuditActor,
           message: str, details: dict[str, Any] | None = None) -> None:
    record_event(
        session,
        event_type=event_type,
        actor=actor,
        run_id=action.run_id,
        action_id=action.id,
        invoice_id=action.invoice_id,
        message=message,
        details=details,
    )


def _label(action: ActionRecord) -> str:
    return f"{action.action_type} for invoice {action.invoice_number or action.invoice_id}"


# ---------- Approval ----------

async def approve_action(session: AsyncSession, action_id: str, confirmed_hash: str) -> ActionRecord:
    action = await get_action(session, action_id)  # Also applies expiry.
    if action.approval_status != ApprovalStatus.PENDING.value:
        raise ConflictError(f"Only pending actions can be approved (current: {action.approval_status}).")

    current_hash = parameters_hash(action.parameters)
    if confirmed_hash != current_hash or action.parameters_hash != current_hash:
        raise ConflictError("The reviewed parameters do not match the current action. Review it again.")

    action.approval_status = ApprovalStatus.APPROVED.value
    action.approved_parameters_hash = current_hash
    action.decided_at = utc_now()
    _audit(session, action, AuditEventType.ACTION_APPROVED, AuditActor.USER,
           f"User approved {_label(action)}.", {"parameters_hash": current_hash})
    await session.commit()
    return action


async def reject_action(session: AsyncSession, action_id: str, reason: str | None) -> ActionRecord:
    action = await get_action(session, action_id)
    if action.approval_status != ApprovalStatus.PENDING.value:
        raise ConflictError(f"Only pending actions can be rejected (current: {action.approval_status}).")

    action.approval_status = ApprovalStatus.REJECTED.value
    action.decided_at = utc_now()
    _audit(session, action, AuditEventType.ACTION_REJECTED, AuditActor.USER,
           f"User rejected {_label(action)}. Nothing will be sent.", {"reason": reason})
    await session.commit()
    return action


# ---------- Execution ----------

def _validated_parameters(action: ActionRecord) -> tuple[ProposedActionType, BaseModel]:
    try:
        action_type = ProposedActionType(action.action_type)
        params = PARAMETER_MODELS[action_type].model_validate(action.parameters)
    except (ValueError, KeyError, ValidationError) as exc:
        raise ConflictError("The stored action parameters are invalid; it cannot be executed.") from exc
    if getattr(params, "invoice_id") != action.invoice_id:
        raise ConflictError("The action parameters do not match the action's invoice.")
    return action_type, params


async def _claim_for_execution(session: AsyncSession, action: ActionRecord) -> None:
    """Atomically move not_started -> executing so an action can run only once."""
    result = await session.execute(
        update(ActionRecord)
        .where(
            ActionRecord.id == action.id,
            ActionRecord.approval_status == ApprovalStatus.APPROVED.value,
            ActionRecord.execution_status == ExecutionStatus.NOT_STARTED.value,
        )
        .values(execution_status=ExecutionStatus.EXECUTING.value)
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        await session.rollback()
        raise ConflictError("This action is already executing or was already executed.")
    _audit(session, action, AuditEventType.EXECUTION_STARTED, AuditActor.SYSTEM,
           f"Executing approved {_label(action)}.")
    await session.commit()
    await session.refresh(action)


async def _call_paypal(api: PayPalInvoicesAPI, action: ActionRecord,
                       action_type: ProposedActionType, params: BaseModel) -> None:
    # The action ID is the PayPal-Request-Id, so PayPal can de-duplicate the request.
    if action_type is ProposedActionType.SEND_INVOICE:
        assert isinstance(params, SendInvoiceParameters)
        await api.send_invoice(
            params.invoice_id,
            request_id=action.id,
            send_to_recipient=params.send_to_recipient,
            send_to_invoicer=params.send_to_invoicer,
            subject=params.subject,
            note=params.note,
        )
    else:
        assert isinstance(params, SendReminderParameters)
        await api.remind_invoice(params.invoice_id, request_id=action.id, subject=params.subject, note=params.note)


async def _finish(
    session: AsyncSession,
    action: ActionRecord,
    *,
    execution_status: ExecutionStatus,
    event_type: AuditEventType,
    message: str,
    verification_status: VerificationStatus = VerificationStatus.NOT_VERIFIED,
    failure_reason: str | None = None,
    request_sent: bool = False,
    details: dict[str, Any] | None = None,
) -> ActionRecord:
    action.execution_status = execution_status.value
    action.verification_status = verification_status.value
    action.failure_reason = failure_reason
    action.executed_at = utc_now()
    if request_sent:
        action.external_reference = f"PayPal-Request-Id:{action.id}"
    _audit(session, action, event_type, AuditActor.SYSTEM, message, details)
    await session.commit()
    return action


async def execute_action(session: AsyncSession, api: PayPalInvoicesAPI, action_id: str) -> ActionRecord:
    action = await get_action(session, action_id)

    if action.approval_status != ApprovalStatus.APPROVED.value:
        raise ConflictError(f"The action must be approved before execution (current: {action.approval_status}).")
    if action.execution_status != ExecutionStatus.NOT_STARTED.value:
        raise ConflictError(
            f"The action was already executed (status: {action.execution_status}). "
            "Executions are never repeated automatically."
        )
    if action.approved_parameters_hash != parameters_hash(action.parameters):
        raise ConflictError("The action parameters changed after approval. A new approval is required.")
    if action.decided_at is None or utc_now() > action.decided_at + EXECUTION_WINDOW:
        raise ConflictError("The approval is older than 15 minutes. Ask the agent for a new proposal.")

    action_type, params = _validated_parameters(action)
    await _claim_for_execution(session, action)

    # 1) Precondition check: PayPal is the source of truth.
    try:
        before = await api.get_invoice(action.invoice_id)
    except PayPalError as exc:
        return await _finish(
            session, action,
            execution_status=ExecutionStatus.FAILED,
            event_type=AuditEventType.EXECUTION_FAILED,
            message="Could not read the invoice from PayPal before executing. Nothing was sent.",
            failure_reason="PayPal was unavailable during the pre-execution check. Nothing was sent.",
            details={"error": type(exc).__name__},
        )

    allowed = PRECONDITION_STATUSES[action_type]
    if before.status not in allowed:
        reason = (
            f"Invoice status is {before.status}; expected {', '.join(sorted(allowed))}. Nothing was sent."
        )
        return await _finish(
            session, action,
            execution_status=ExecutionStatus.FAILED,
            event_type=AuditEventType.EXECUTION_BLOCKED,
            message=f"Blocked: {reason}",
            failure_reason=reason,
            details={"status_before": before.status},
        )

    # 2) Execute the approved operation.
    outcome_unknown = False
    try:
        await _call_paypal(api, action, action_type, params)
    except PayPalWriteOutcomeUnknownError:
        outcome_unknown = True
    except PayPalConnectionError:
        return await _finish(
            session, action,
            execution_status=ExecutionStatus.FAILED,
            event_type=AuditEventType.EXECUTION_FAILED,
            message="Could not connect to PayPal. Nothing was sent.",
            failure_reason="Could not connect to PayPal. Nothing was sent.",
        )
    except PayPalAPIError as exc:
        return await _finish(
            session, action,
            execution_status=ExecutionStatus.FAILED,
            event_type=AuditEventType.EXECUTION_FAILED,
            message=f"PayPal rejected the request (HTTP {exc.status_code}).",
            failure_reason=f"PayPal rejected the request (HTTP {exc.status_code}).",
            request_sent=True,
            details={"paypal_debug_id": exc.debug_id, "paypal_message": str(exc)[:300]},
        )

    # 3) Verify by reading PayPal again.
    try:
        status_after: str | None = (await api.get_invoice(action.invoice_id)).status
    except PayPalError:
        status_after = None

    if status_after in VERIFIED_STATUSES[action_type]:
        verification = VerificationStatus.VERIFIED
    elif status_after is None:
        verification = VerificationStatus.NOT_VERIFIED
    else:
        verification = VerificationStatus.MISMATCH

    _audit(session, action, AuditEventType.VERIFICATION_COMPLETED, AuditActor.SYSTEM,
           f"PayPal now reports status {status_after or 'unavailable'} ({verification.value}).",
           {"status_before": before.status, "status_after": status_after})

    confirmed_despite_timeout = (
        outcome_unknown
        and action_type is ProposedActionType.SEND_INVOICE
        and verification is VerificationStatus.VERIFIED
    )
    if outcome_unknown and not confirmed_despite_timeout:
        reason = (
            "The PayPal request timed out; it may or may not have been applied. "
            "It will not be retried automatically. Check PayPal before taking further action."
        )
        return await _finish(
            session, action,
            execution_status=ExecutionStatus.OUTCOME_UNKNOWN,
            event_type=AuditEventType.EXECUTION_OUTCOME_UNKNOWN,
            message=reason,
            failure_reason=reason,
            request_sent=True,
        )

    suffix = " (response was lost, but PayPal shows the invoice as sent)" if confirmed_despite_timeout else ""
    return await _finish(
        session, action,
        execution_status=ExecutionStatus.SUCCEEDED,
        verification_status=verification,
        event_type=AuditEventType.EXECUTION_SUCCEEDED,
        message=f"PayPal accepted {_label(action)}{suffix}.",
        request_sent=True,
        details={"status_after": status_after},
    )
