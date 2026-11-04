"""Proposed action endpoints: list, approve, reject, execute."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.dependencies import get_paypal_client
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.schemas.actions import (
    ActionListResponse,
    ActionResponse,
    ApprovalStatus,
    ApproveActionRequest,
    RejectActionRequest,
)
from app.services.actions import get_action, list_actions
from app.services.approvals import approve_action, execute_action, reject_action

router = APIRouter(prefix="/actions", tags=["actions"])

ActionId = Annotated[str, Path(pattern=r"^[0-9a-fA-F-]{36}$")]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=ActionListResponse)
async def list_actions_route(
    session: Session,
    approval_status: ApprovalStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ActionListResponse:
    actions = await list_actions(session, approval_status=approval_status, limit=limit)
    return ActionListResponse(items=[ActionResponse.model_validate(action) for action in actions])


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action_route(action_id: ActionId, session: Session) -> ActionResponse:
    return ActionResponse.model_validate(await get_action(session, action_id))


@router.post("/{action_id}/approve", response_model=ActionResponse)
async def approve_action_route(action_id: ActionId, body: ApproveActionRequest, session: Session) -> ActionResponse:
    """Approve the exact parameter version the user reviewed. Does not execute."""
    return ActionResponse.model_validate(await approve_action(session, action_id, body.parameters_hash))


@router.post("/{action_id}/reject", response_model=ActionResponse)
async def reject_action_route(
    action_id: ActionId,
    session: Session,
    body: RejectActionRequest | None = None,
) -> ActionResponse:
    reason = body.reason if body else None
    return ActionResponse.model_validate(await reject_action(session, action_id, reason))


@router.post("/{action_id}/execute", response_model=ActionResponse)
async def execute_action_route(
    action_id: ActionId,
    session: Session,
    client: Annotated[PayPalClient, Depends(get_paypal_client)],
) -> ActionResponse:
    """Execute an approved action in PayPal, then verify the result."""
    return ActionResponse.model_validate(await execute_action(session, PayPalInvoicesAPI(client), action_id))
