"""Collection Autopilot endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dependencies import get_optional_llm
from app.agent.llm import LLM
from app.api.dependencies import get_invoice_service, get_today
from app.core.config import get_settings
from app.db.session import get_session
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.dependencies import get_paypal_client
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.schemas.autopilot import AutopilotRunResponse, AutopilotSettingsResponse, AutopilotSettingsUpdate
from app.services.autopilot import AutopilotService, get_settings_record, settings_response, update_settings
from app.services.invoices import InvoiceService

router = APIRouter(prefix="/autopilot", tags=["autopilot"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/settings", response_model=AutopilotSettingsResponse)
async def get_autopilot_settings(session: Session) -> AutopilotSettingsResponse:
    record = await get_settings_record(session)
    return settings_response(record, get_settings().autopilot_interval_minutes)


@router.put("/settings", response_model=AutopilotSettingsResponse)
async def update_autopilot_settings(body: AutopilotSettingsUpdate, session: Session) -> AutopilotSettingsResponse:
    return await update_settings(session, body, get_settings().autopilot_interval_minutes)


@router.post("/run", response_model=AutopilotRunResponse)
async def run_autopilot(
    session: Session,
    service: Annotated[InvoiceService, Depends(get_invoice_service)],
    client: Annotated[PayPalClient, Depends(get_paypal_client)],
    llm: Annotated[LLM | None, Depends(get_optional_llm)],
    today: Annotated[date, Depends(get_today)],
) -> AutopilotRunResponse:
    """Run the collection playbook now. Returns proposals, auto-executed actions and skips."""
    autopilot = AutopilotService(
        session, service, PayPalInvoicesAPI(client), llm, today, get_settings().business_timezone
    )
    return await autopilot.run(trigger="manual")
