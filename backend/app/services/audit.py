"""Audit trail service. Never store secrets or tokens in audit events."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEventRecord
from app.db.types import utc_now
from app.schemas.audit import AuditActor


def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor: AuditActor,
    message: str,
    run_id: str | None = None,
    action_id: str | None = None,
    invoice_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the session. The caller commits."""
    session.add(
        AuditEventRecord(
            created_at=utc_now(),
            event_type=str(event_type),
            actor=actor.value,
            run_id=run_id,
            action_id=action_id,
            invoice_id=invoice_id,
            message=message[:1000],
            details=details or {},
        )
    )


async def list_events(
    session: AsyncSession,
    *,
    limit: int = 100,
    run_id: str | None = None,
    action_id: str | None = None,
) -> list[AuditEventRecord]:
    query = select(AuditEventRecord).order_by(AuditEventRecord.id.desc()).limit(limit)
    if run_id:
        query = query.where(AuditEventRecord.run_id == run_id)
    if action_id:
        query = query.where(AuditEventRecord.action_id == action_id)
    return list((await session.execute(query)).scalars())
