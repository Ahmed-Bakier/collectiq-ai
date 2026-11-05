"""Safety report endpoint (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.safety import SafetyReport
from app.services.safety import build_safety_report

router = APIRouter(prefix="/safety", tags=["safety"])


@router.get("", response_model=SafetyReport)
async def get_safety_report(session: Annotated[AsyncSession, Depends(get_session)]) -> SafetyReport:
    """Guardrails plus live evidence from the audit trail."""
    return await build_safety_report(session)
