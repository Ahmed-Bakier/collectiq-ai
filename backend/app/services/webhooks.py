"""PayPal webhook events: verify, de-duplicate, re-read PayPal, act, audit.

PayPal stays the source of truth: the event only tells us WHICH invoice changed;
the invoice is read again from PayPal before anything is done. Every verified
event leaves a trace in the audit trail, including events we do not act on.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionRecord, WebhookEventRecord
from app.db.types import utc_now
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.invoices import INVOICE_ID_PATTERN, PayPalInvoicesAPI
from app.integrations.paypal.webhooks import verify_webhook_signature
from app.schemas.actions import ApprovalStatus
from app.schemas.audit import AuditActor, AuditEventType
from app.services.audit import record_event
from app.services.client_insights import client_key
from app.services.invoices import to_invoice_summary

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 256 * 1024
INVOICE_ID_PREFIX = "INV2-"
FULLY_PAID = frozenset({"PAID", "MARKED_AS_PAID", "PAID_EXTERNAL"})
PAYMENT_STATUSES = FULLY_PAID | {"PARTIALLY_PAID"}


class WebhookRejectedError(Exception):
    """The request is not a valid, PayPal-signed webhook event."""


@dataclass(frozen=True)
class WebhookResult:
    status: str  # processed | duplicate | ignored
    event_type: str | None = None
    invoice_id: str | None = None


def extract_invoice_id(resource: Any) -> str | None:
    """PayPal sends the invoice nested (resource.invoice) or flat (resource); accept both."""
    if not isinstance(resource, dict):
        return None
    nested = resource.get("invoice")
    candidates = [nested.get("id") if isinstance(nested, dict) else None, resource.get("id")]
    for candidate in candidates:
        if (
            isinstance(candidate, str)
            and candidate.startswith(INVOICE_ID_PREFIX)
            and INVOICE_ID_PATTERN.fullmatch(candidate)
        ):
            return candidate
    return None


class PayPalWebhookService:
    def __init__(self, session: AsyncSession, client: PayPalClient, webhook_id: str) -> None:
        self._session = session
        self._client = client
        self._webhook_id = webhook_id
        self._invoices = PayPalInvoicesAPI(client)

    async def handle(self, headers: Mapping[str, str], raw_body: bytes) -> WebhookResult:
        if len(raw_body) > MAX_BODY_BYTES:
            raise WebhookRejectedError("Event body is too large.")
        try:
            event = json.loads(raw_body)
        except ValueError as exc:
            raise WebhookRejectedError("Event body is not valid JSON.") from exc
        if not isinstance(event, dict) or not isinstance(event.get("id"), str):
            raise WebhookRejectedError("Not a PayPal webhook event.")

        event_id = event["id"][:64]
        event_type = str(event.get("event_type") or "")[:80]
        if await self._session.get(WebhookEventRecord, event_id) is not None:
            logger.info("PayPal webhook %s (%s): duplicate, skipped.", event_id, event_type)
            return WebhookResult("duplicate", event_type)

        if not await verify_webhook_signature(self._client, headers, event, self._webhook_id):
            logger.warning("PayPal webhook %s (%s): signature verification failed.", event_id, event_type)
            raise WebhookRejectedError("PayPal signature verification failed.")

        resource = event.get("resource")
        invoice_id = extract_invoice_id(resource)
        if invoice_id is None or not event_type.startswith("INVOICING.INVOICE."):
            # Verified but not actionable: leave a trace, and do not mark it as processed,
            # so PayPal's "Resend" works after a fix.
            keys = sorted(resource.keys())[:20] if isinstance(resource, dict) else []
            record_event(
                self._session,
                event_type=AuditEventType.WEBHOOK_RECEIVED,
                actor=AuditActor.SYSTEM,
                message=f"PayPal event {event_type or 'unknown'} received without an invoice reference; no action taken.",
                details={"event_id": event_id, "resource_keys": keys},
            )
            await self._session.commit()
            logger.info("PayPal webhook %s (%s): no invoice reference (resource keys %s).", event_id, event_type, keys)
            return WebhookResult("ignored", event_type)

        await self._apply_invoice_event(event_type, invoice_id)
        # Stored in the same commit as its effects, so a failed attempt is retried by PayPal.
        self._session.add(
            WebhookEventRecord(id=event_id, event_type=event_type, resource_id=invoice_id, received_at=utc_now())
        )
        await self._session.commit()
        logger.info("PayPal webhook %s (%s): processed for invoice %s.", event_id, event_type, invoice_id)
        return WebhookResult("processed", event_type, invoice_id)

    async def _apply_invoice_event(self, event_type: str, invoice_id: str) -> None:
        invoice = await self._invoices.get_invoice(invoice_id)  # PayPal is the source of truth.
        summary = to_invoice_summary(invoice)
        client = client_key(summary)
        number = summary.invoice_number or invoice_id
        status = invoice.status.upper()

        if event_type == "INVOICING.INVOICE.PAID" and status in PAYMENT_STATUSES:
            paid = invoice.payments.paid_amount if invoice.payments else None
            amount = f"{paid.value} {paid.currency_code}" if paid else "a payment"
            record_event(
                self._session,
                event_type=AuditEventType.PAYMENT_RECEIVED,
                actor=AuditActor.SYSTEM,
                invoice_id=invoice_id,
                message=f"Payment received from {client} for invoice {number}: {amount} (PayPal status {status}).",
                details={"paypal_event": event_type, "status": status},
            )
            if status in FULLY_PAID:
                await self._withdraw_pending(invoice_id, "the invoice was paid")
            return

        if event_type == "INVOICING.INVOICE.CANCELLED":
            record_event(
                self._session,
                event_type=AuditEventType.WEBHOOK_RECEIVED,
                actor=AuditActor.SYSTEM,
                invoice_id=invoice_id,
                message=f"Invoice {number} for {client} was cancelled in PayPal.",
                details={"paypal_event": event_type, "status": status},
            )
            await self._withdraw_pending(invoice_id, "the invoice was cancelled")
            return

        record_event(
            self._session,
            event_type=AuditEventType.WEBHOOK_RECEIVED,
            actor=AuditActor.SYSTEM,
            invoice_id=invoice_id,
            message=f"PayPal event {event_type} for invoice {number} ({client}); PayPal status {status}.",
            details={"paypal_event": event_type, "status": status},
        )

    async def _withdraw_pending(self, invoice_id: str, reason: str) -> None:
        result = await self._session.execute(
            select(ActionRecord).where(
                ActionRecord.invoice_id == invoice_id,
                ActionRecord.approval_status == ApprovalStatus.PENDING.value,
            )
        )
        for action in result.scalars():
            action.approval_status = ApprovalStatus.SUPERSEDED.value
            record_event(
                self._session,
                event_type=AuditEventType.ACTION_SUPERSEDED,
                actor=AuditActor.SYSTEM,
                run_id=action.run_id,
                action_id=action.id,
                invoice_id=invoice_id,
                message=f"Withdrawn: {reason} (PayPal webhook). No approval is needed anymore.",
                details={"reason": reason},
            )
