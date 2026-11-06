"""CollectIQ collection agent: a bounded tool-calling loop."""

import json
import uuid
from datetime import date, datetime
from typing import Any

from app.agent.llm import LLM
from app.agent.prompts import build_system_prompt
from app.agent.tools import TOOL_DEFINITIONS, AgentRunContext, execute_tool
from app.schemas.agent import AgentRunResponse, AgentRunStatus
from app.schemas.analysis import SuggestedAction
from app.services.invoices import InvoiceService

MAX_AGENT_STEPS = 6
MAX_TOOL_CALLS = 15
INCOMPLETE_SUMMARY = (
    "The assistant stopped before finishing. Please try again with a more specific request."
)


class CollectionAgent:
    def __init__(
        self,
        llm: LLM,
        invoice_service: InvoiceService,
        today: date,
        timezone: str,
        last_reminders: dict[str, datetime] | None = None,
    ) -> None:
        self._llm = llm
        self._invoice_service = invoice_service
        self._today = today
        self._timezone = timezone
        self._last_reminders = last_reminders or {}

    async def run(self, user_message: str) -> AgentRunResponse:
        context = AgentRunContext(
            invoice_service=self._invoice_service,
            today=self._today,
            timezone=self._timezone,
            last_reminders=self._last_reminders,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(self._today, self._timezone)},
            {"role": "user", "content": user_message},
        ]

        summary: str | None = None
        tool_calls_used = 0

        for _ in range(MAX_AGENT_STEPS):
            response = await self._llm.complete(messages, TOOL_DEFINITIONS)
            messages.append(response.raw_message or {"role": "assistant", "content": response.content})

            if not response.tool_calls:
                summary = (response.content or "").strip() or "No summary was produced."
                break

            for call in response.tool_calls:
                tool_calls_used += 1
                if tool_calls_used > MAX_TOOL_CALLS:
                    result: dict[str, Any] = {"error": "Tool call limit reached for this run."}
                else:
                    result = await execute_tool(context, call.name, call.arguments)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)}
                )

        if summary is None:
            status = AgentRunStatus.INCOMPLETE
            summary = INCOMPLETE_SUMMARY
        elif context.proposals:
            status = AgentRunStatus.AWAITING_APPROVAL
        else:
            status = AgentRunStatus.COMPLETED

        findings = (
            [item for item in context.analysis.invoices if item.suggested_action is not SuggestedAction.NONE]
            if context.analysis
            else []
        )

        return AgentRunResponse(
            run_id=str(uuid.uuid4()),
            model=self._llm.model,
            summary=summary,
            status=status,
            requires_approval=bool(context.proposals),
            findings=findings,
            proposed_actions=context.proposals,
            tool_calls=context.tool_records,
        )
