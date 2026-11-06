"""AI agent endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import CollectionAgent
from app.agent.dependencies import get_llm
from app.agent.llm import LLM
from app.api.dependencies import get_invoice_service, get_today
from app.core.config import get_settings
from app.db.session import get_session
from app.schemas.agent import AgentRunRequest, AgentRunResponse
from app.services.actions import save_agent_run
from app.services.invoices import InvoiceService
from app.services.reminders import last_reminders

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/runs", response_model=AgentRunResponse)
async def create_agent_run(
    request: AgentRunRequest,
    llm: Annotated[LLM, Depends(get_llm)],
    service: Annotated[InvoiceService, Depends(get_invoice_service)],
    today: Annotated[date, Depends(get_today)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRunResponse:
    """Run the collection agent. Proposed actions are stored, never executed here."""
    agent = CollectionAgent(
        llm,
        service,
        today=today,
        timezone=get_settings().business_timezone,
        last_reminders=await last_reminders(session),
    )
    result = await agent.run(request.message)
    await save_agent_run(session, request.message, result)
    return result
