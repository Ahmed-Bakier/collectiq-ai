"""AI agent endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.agent import CollectionAgent
from app.agent.dependencies import get_llm
from app.agent.llm import LLM
from app.api.dependencies import get_invoice_service, get_today
from app.core.config import get_settings
from app.schemas.agent import AgentRunRequest, AgentRunResponse
from app.services.invoices import InvoiceService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/runs", response_model=AgentRunResponse)
async def create_agent_run(
    request: AgentRunRequest,
    llm: Annotated[LLM, Depends(get_llm)],
    service: Annotated[InvoiceService, Depends(get_invoice_service)],
    today: Annotated[date, Depends(get_today)],
) -> AgentRunResponse:
    """Run the collection agent. Proposed actions are returned, never executed."""
    agent = CollectionAgent(llm, service, today=today, timezone=get_settings().business_timezone)
    return await agent.run(request.message)
