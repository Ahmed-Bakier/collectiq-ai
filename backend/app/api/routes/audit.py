"""Audit trail endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.audit import AuditEventResponse, AuditListResponse
from app.services.audit import list_events

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
async def list_audit_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    run_id: str | None = None,
    action_id: str | None = None,
) -> AuditListResponse:
    """Audit events, newest first."""
    events = await list_events(session, limit=limit, run_id=run_id, action_id=action_id)
    return AuditListResponse(items=[AuditEventResponse.model_validate(event) for event in events])
