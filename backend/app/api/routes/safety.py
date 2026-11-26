"""Safety endpoints: report with live evidence, and an on-demand message check."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.message_guard import check_message
from app.db.session import get_session
from app.schemas.safety import MessageCheckRequest, MessageCheckResponse, SafetyReport
from app.services.safety import build_safety_report

router = APIRouter(prefix="/safety", tags=["safety"])


@router.get("", response_model=SafetyReport)
async def get_safety_report(session: Annotated[AsyncSession, Depends(get_session)]) -> SafetyReport:
    """Guardrails plus live evidence from the audit trail."""
    return await build_safety_report(session)


@router.post("/check-message", response_model=MessageCheckResponse)
async def check_client_message(body: MessageCheckRequest) -> MessageCheckResponse:
    """Run the deterministic message safety check on any text (no side effects)."""
    violations = check_message(body.text)
    return MessageCheckResponse(passed=not violations, violations=violations)
