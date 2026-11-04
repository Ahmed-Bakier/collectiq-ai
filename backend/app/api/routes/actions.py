"""Proposed action endpoints (read). Approval and execution come next."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.actions import ActionListResponse, ActionResponse, ApprovalStatus
from app.services.actions import get_action, list_actions

router = APIRouter(prefix="/actions", tags=["actions"])

ACTION_ID_PATTERN = r"^[0-9a-fA-F-]{36}$"


@router.get("", response_model=ActionListResponse)
async def list_actions_route(
    session: Annotated[AsyncSession, Depends(get_session)],
    approval_status: ApprovalStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ActionListResponse:
    actions = await list_actions(session, approval_status=approval_status, limit=limit)
    return ActionListResponse(items=[ActionResponse.model_validate(action) for action in actions])


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action_route(
    action_id: Annotated[str, Path(pattern=ACTION_ID_PATTERN)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActionResponse:
    return ActionResponse.model_validate(await get_action(session, action_id))
