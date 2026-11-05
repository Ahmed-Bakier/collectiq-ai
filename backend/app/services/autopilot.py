"""Collection Autopilot.

A deterministic playbook decides WHICH invoices need action, WHICH action and
WHICH tone (escalated one step for high-risk clients, from PayPal payment
history). The LLM only drafts the client message (templates are the fallback).
Every action is proposed and audited. Auto-approval is limited to a strict,
user-enabled policy: friendly reminders up to a maximum amount, never for
high-risk clients. Invoices are never sent automatically.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.drafting import draft_from_facts
from app.agent.llm import LLM, LLMError
from app.agent.tools import ProposeActionArgs, build_proposal
from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.db.models import ActionRecord, AutopilotSettingsRecord
from app.db.types import utc_now
from app.integrations.paypal.invoices import PayPalInvoicesAPI
from app.schemas.actions import ActionResponse, ApprovalStatus, ExecutionStatus, MessageTone
from app.schemas.agent import AgentRunResponse, AgentRunStatus, ProposedAction, ProposedActionType
from app.schemas.analysis import AnalyzedInvoice, CollectionState, SuggestedAction
from app.schemas.audit import AuditActor, AuditEventType
from app.schemas.autopilot import (
    AutopilotProposal,
    AutopilotRunResponse,
    AutopilotSettingsResponse,
    AutopilotSettingsUpdate,
    SkippedInvoice,
)
from app.schemas.insights import RiskLevel
from app.services.actions import save_agent_run
from app.services.approvals import approve_action, execute_action
from app.services.audit import record_event
from app.services.client_insights import ClientInsightsService, build_insights, client_key
from app.services.invoice_analysis import analyze_invoices, collectible_amount
from app.services.invoices import InvoiceService, to_invoice_summary

logger = logging.getLogger(__name__)

SETTINGS_ID = 1
REMINDER_COOLDOWN = timedelta(days=3)
MAX_AUTO_ACTIONS_PER_RUN = 5

PLAYBOOK_ACTIONS: dict[SuggestedAction, ProposedActionType] = {
    SuggestedAction.SEND_INVOICE: ProposedActionType.SEND_INVOICE,
    SuggestedAction.SEND_REMINDER: ProposedActionType.SEND_REMINDER,
}


# ---------- Playbook rules (deterministic) ----------

def playbook_tone(item: AnalyzedInvoice, risk: RiskLevel | None = None) -> MessageTone:
    """Escalation ladder based on days overdue; one step firmer for high-risk clients."""
    days = item.days_overdue or 0
    overdue = item.collection_state is CollectionState.OVERDUE
    if overdue and days > 21:
        return MessageTone.FINAL_NOTICE
    if overdue and (days > 7 or risk is RiskLevel.HIGH):
        return MessageTone.FIRM
    return MessageTone.FRIENDLY


def _client(item: AnalyzedInvoice) -> str | None:
    return item.invoice.recipient_business_name or item.invoice.recipient_name


def fallback_message(item: AnalyzedInvoice, action_type: ProposedActionType, tone: MessageTone) -> str:
    """Deterministic template used when the LLM is unavailable."""
    invoice = item.invoice
    contact = invoice.recipient_name or "there"
    number = invoice.invoice_number or invoice.id
    owed = collectible_amount(invoice)
    amount = f"{owed} {invoice.currency_code or ''}".strip() if owed is not None else "the amount due"
    days = item.days_overdue or 0

    if action_type is ProposedActionType.SEND_INVOICE:
        return f"Hi {contact}, please find invoice {number} for {amount}. Thank you for your business!"
    if tone is MessageTone.FINAL_NOTICE:
        return (
            f"Hi {contact}, this is a final notice that invoice {number} for {amount} is {days} days overdue. "
            "Please arrange payment as soon as possible or contact us to discuss."
        )
    if tone is MessageTone.FIRM:
        return (
            f"Hi {contact}, invoice {number} for {amount} is now {days} days overdue. "
            "Please arrange payment or let us know your expected payment date."
        )
    if days:
        return f"Hi {contact}, a friendly reminder that invoice {number} for {amount} was due {days} days ago. Thank you!"
    return f"Hi {contact}, a friendly reminder that invoice {number} for {amount} is due today. Thank you!"


# ---------- Settings ----------

async def get_settings_record(session: AsyncSession) -> AutopilotSettingsRecord:
    record = await session.get(AutopilotSettingsRecord, SETTINGS_ID)
    if record is None:
        record = AutopilotSettingsRecord(
            id=SETTINGS_ID,
            enabled=True,
            auto_approve_enabled=False,
            auto_approve_max_amount="500.00",
            updated_at=utc_now(),
        )
        session.add(record)
        await session.commit()
    return record


def settings_response(record: AutopilotSettingsRecord, interval_minutes: int) -> AutopilotSettingsResponse:
    return AutopilotSettingsResponse(
        enabled=record.enabled,
        auto_approve_enabled=record.auto_approve_enabled,
        auto_approve_max_amount=Decimal(record.auto_approve_max_amount),
        cooldown_days=REMINDER_COOLDOWN.days,
        max_auto_actions_per_run=MAX_AUTO_ACTIONS_PER_RUN,
        schedule_interval_minutes=interval_minutes,
        last_run_at=record.last_run_at,
    )


async def update_settings(
    session: AsyncSession,
    update: AutopilotSettingsUpdate,
    interval_minutes: int,
) -> AutopilotSettingsResponse:
    record = await get_settings_record(session)
    changes: dict[str, Any] = update.model_dump(exclude_none=True)
    if "auto_approve_max_amount" in changes:
        changes["auto_approve_max_amount"] = f"{changes['auto_approve_max_amount']:.2f}"
    for key, value in changes.items():
        setattr(record, key, value)
    record.updated_at = utc_now()

    summary = ", ".join(f"{key}={value}" for key, value in changes.items()) or "no changes"
    record_event(
        session,
        event_type=AuditEventType.AUTOPILOT_SETTINGS_CHANGED,
        actor=AuditActor.USER,
        message=f"Autopilot settings changed: {summary}.",
        details={key: str(value) for key, value in changes.items()},
    )
    await session.commit()
    return settings_response(record, interval_minutes)


# ---------- Run ----------

class AutopilotService:
    def __init__(
        self,
        session: AsyncSession,
        invoice_service: InvoiceService,
        invoices_api: PayPalInvoicesAPI,
        llm: LLM | None,
        today: date,
        timezone: str,
    ) -> None:
        self._session = session
        self._invoice_service = invoice_service
        self._invoices_api = invoices_api
        self._llm = llm
        self._today = today
        self._timezone = timezone

    async def run(self, trigger: str) -> AutopilotRunResponse:
        settings = await get_settings_record(self._session)
        if not settings.enabled:
            raise ConflictError("Autopilot is paused. Turn it on to run the collection playbook.")

        # One PayPal read feeds both the collection analysis and the client risk levels.
        raw_invoices = await ClientInsightsService(self._invoice_service).load_invoices()
        invoices = [to_invoice_summary(invoice) for invoice in raw_invoices]
        analysis = analyze_invoices(invoices, today=self._today, timezone=self._timezone)
        insights = build_insights(raw_invoices, self._today, self._timezone)
        risks = {insight.client: insight.risk_level for insight in insights.clients}

        history = await self._actions_by_invoice({item.invoice.id for item in analysis.invoices})
        now = utc_now()

        proposals: list[ProposedAction] = []
        tones: dict[str, MessageTone] = {}
        client_risks: dict[str, RiskLevel | None] = {}
        skipped: list[SkippedInvoice] = []
        eligible = 0
        fallback_used = False

        for item in analysis.invoices:
            action_type = PLAYBOOK_ACTIONS.get(item.suggested_action)
            if action_type is None:
                continue
            eligible += 1

            skip_reason = self._skip_reason(action_type, history.get(item.invoice.id, []), now)
            if skip_reason:
                skipped.append(
                    SkippedInvoice(
                        invoice_id=item.invoice.id,
                        invoice_number=item.invoice.invoice_number,
                        client=_client(item),
                        reason=skip_reason,
                    )
                )
                continue

            risk = risks.get(client_key(item.invoice))
            tone = playbook_tone(item, risk)
            message, used_fallback = await self._draft(item, action_type, tone)
            fallback_used = fallback_used or used_fallback
            proposal = build_proposal(
                item,
                ProposeActionArgs(
                    invoice_id=item.invoice.id,
                    action_type=action_type,
                    reason=self._reason(item, tone, risk),
                    message_to_client=message,
                ),
            )
            proposals.append(proposal)
            tones[proposal.id] = tone
            client_risks[proposal.id] = risk

        run = AgentRunResponse(
            run_id=str(uuid.uuid4()),
            model=f"autopilot-playbook ({self._llm.model if self._llm else 'templates'})",
            summary=f"Autopilot evaluated {len(analysis.invoices)} invoices and prepared {len(proposals)} action(s).",
            status=AgentRunStatus.AWAITING_APPROVAL if proposals else AgentRunStatus.COMPLETED,
            requires_approval=bool(proposals),
            findings=[],
            proposed_actions=proposals,
            tool_calls=[],
        )
        await save_agent_run(self._session, f"Autopilot run ({trigger})", run, requested_by=AuditActor.SYSTEM)

        results: list[AutopilotProposal] = []
        auto_count = 0
        for proposal in proposals:
            tone = tones[proposal.id]
            risk = client_risks[proposal.id]
            record = await self._session.get(ActionRecord, proposal.id)
            assert record is not None
            auto = False
            if auto_count < MAX_AUTO_ACTIONS_PER_RUN and self._auto_approvable(settings, proposal, tone, risk):
                policy = f"friendly reminder up to {settings.auto_approve_max_amount}"
                await approve_action(
                    self._session,
                    proposal.id,
                    record.parameters_hash,
                    approved_by=AuditActor.SYSTEM,
                    policy=policy,
                )
                record = await execute_action(self._session, self._invoices_api, proposal.id)
                auto = True
                auto_count += 1
            results.append(
                AutopilotProposal(
                    action=ActionResponse.model_validate(record),
                    tone=tone,
                    auto_approved=auto,
                    client_risk=risk,
                )
            )

        settings.last_run_at = now
        summary = (
            f"Autopilot ({trigger}) evaluated {len(analysis.invoices)} invoices: {len(proposals)} proposed, "
            f"{auto_count} auto-executed, {len(skipped)} skipped."
        )
        record_event(
            self._session,
            event_type=AuditEventType.AUTOPILOT_RUN_COMPLETED,
            actor=AuditActor.SYSTEM,
            run_id=run.run_id,
            message=summary,
            details={
                "trigger": trigger,
                "proposed": len(proposals),
                "auto_executed": auto_count,
                "skipped": len(skipped),
                "llm_fallback_used": fallback_used,
            },
        )
        await self._session.commit()

        return AutopilotRunResponse(
            run_id=run.run_id,
            trigger=trigger,
            summary=summary,
            evaluated_invoices=len(analysis.invoices),
            eligible_invoices=eligible,
            auto_executed_count=auto_count,
            llm_fallback_used=fallback_used,
            proposals=results,
            skipped=skipped,
        )

    async def _actions_by_invoice(self, invoice_ids: set[str]) -> dict[str, list[ActionRecord]]:
        grouped: dict[str, list[ActionRecord]] = defaultdict(list)
        if not invoice_ids:
            return grouped
        result = await self._session.execute(select(ActionRecord).where(ActionRecord.invoice_id.in_(invoice_ids)))
        for action in result.scalars():
            grouped[action.invoice_id].append(action)
        return grouped

    @staticmethod
    def _skip_reason(action_type: ProposedActionType, actions: list[ActionRecord], now: datetime) -> str | None:
        for action in actions:
            if action.action_type != action_type.value:
                continue
            if action.approval_status == ApprovalStatus.PENDING.value and action.expires_at > now:
                return "A proposal for this invoice is already awaiting approval."
            if (
                action_type is ProposedActionType.SEND_REMINDER
                and action.execution_status == ExecutionStatus.SUCCEEDED.value
                and action.executed_at is not None
                and now - action.executed_at < REMINDER_COOLDOWN
            ):
                return f"A reminder was sent less than {REMINDER_COOLDOWN.days} days ago."
        return None

    async def _draft(self, item: AnalyzedInvoice, action_type: ProposedActionType, tone: MessageTone) -> tuple[str, bool]:
        if self._llm is not None:
            facts = {
                "purpose": "send the invoice"
                if action_type is ProposedActionType.SEND_INVOICE
                else "remind about an unpaid invoice",
                "client": _client(item),
                "contact_name": item.invoice.recipient_name,
                "invoice_number": item.invoice.invoice_number,
                "amount": collectible_amount(item.invoice),
                "currency": item.invoice.currency_code,
                "due_date": item.invoice.due_date,
                "days_overdue": item.days_overdue,
            }
            try:
                return await draft_from_facts(self._llm, facts, tone, "en"), False
            except LLMError:
                logger.warning("Autopilot drafting failed; using a template message.")
        return fallback_message(item, action_type, tone), True

    @staticmethod
    def _reason(item: AnalyzedInvoice, tone: MessageTone, risk: RiskLevel | None) -> str:
        evidence = item.reasons[1] if len(item.reasons) > 1 else item.collection_state.value
        reason = f"Playbook: {evidence}; {tone.value.replace('_', ' ')} tone"
        if tone is not playbook_tone(item):
            reason += "; escalated one step because this client usually pays late (high risk)"
        return reason + "."

    @staticmethod
    def _auto_approvable(
        settings: AutopilotSettingsRecord,
        proposal: ProposedAction,
        tone: MessageTone,
        risk: RiskLevel | None,
    ) -> bool:
        """Strict policy: only friendly reminders up to the user's limit. Never invoices or high-risk clients."""
        if not settings.auto_approve_enabled or risk is RiskLevel.HIGH:
            return False
        if proposal.action_type is not ProposedActionType.SEND_REMINDER or tone is not MessageTone.FRIENDLY:
            return False
        if proposal.amount is None:
            return False
        try:
            limit = Decimal(settings.auto_approve_max_amount)
        except InvalidOperation:
            return False
        return proposal.amount <= limit


# ---------- Background schedule ----------

async def run_scheduled_autopilot() -> None:
    from app.agent.dependencies import get_optional_llm
    from app.db.session import get_sessionmaker
    from app.integrations.paypal.dependencies import get_paypal_client

    app_settings = get_settings()
    client = get_paypal_client()
    api = PayPalInvoicesAPI(client)
    today = datetime.now(ZoneInfo(app_settings.business_timezone)).date()

    async with get_sessionmaker()() as session:
        service = AutopilotService(
            session, InvoiceService(api), api, get_optional_llm(), today, app_settings.business_timezone
        )
        try:
            result = await service.run(trigger="scheduled")
            logger.info("Scheduled autopilot: %s", result.summary)
        except ConflictError as exc:
            logger.info("Scheduled autopilot skipped: %s", exc.message)


async def autopilot_scheduler(interval_minutes: int) -> None:
    """Runs the autopilot every N minutes while the app is running."""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await run_scheduled_autopilot()
        except Exception:  # noqa: BLE001 - the scheduler must keep running
            logger.exception("Scheduled autopilot run failed.")
