"""PayPal webhook receiver."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.dependencies import get_paypal_client
from app.services.webhooks import PayPalWebhookService, WebhookRejectedError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "paypal_debug_id": None}},
    )


@router.post("/paypal")
async def paypal_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    client: Annotated[PayPalClient, Depends(get_paypal_client)],
) -> JSONResponse:
    """Receive a PayPal webhook event. Only PayPal-signed events are processed, each once."""
    webhook_id = (get_settings().paypal_webhook_id or "").strip()
    if not webhook_id:
        return _error(503, "webhooks_not_configured", "Set PAYPAL_WEBHOOK_ID to receive PayPal webhooks.")
    try:
        result = await PayPalWebhookService(session, client, webhook_id).handle(request.headers, await request.body())
    except WebhookRejectedError as exc:
        return _error(400, "webhook_rejected", str(exc))
    return JSONResponse({"status": result.status, "event_type": result.event_type, "invoice_id": result.invoice_id})
