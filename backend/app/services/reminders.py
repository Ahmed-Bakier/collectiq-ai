"""Reminder history used to prevent repeated reminders (anti-spam)."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionRecord
from app.schemas.actions import ExecutionStatus
from app.schemas.agent import ProposedActionType

REMINDER_COOLDOWN = timedelta(days=3)


async def last_reminders(session: AsyncSession) -> dict[str, datetime]:
    """Latest successfully executed reminder per invoice."""
    result = await session.execute(
        select(ActionRecord.invoice_id, func.max(ActionRecord.executed_at))
        .where(
            ActionRecord.action_type == ProposedActionType.SEND_REMINDER.value,
            ActionRecord.execution_status == ExecutionStatus.SUCCEEDED.value,
            ActionRecord.executed_at.is_not(None),
        )
        .group_by(ActionRecord.invoice_id)
    )
    return {invoice_id: executed_at for invoice_id, executed_at in result.all() if executed_at is not None}
