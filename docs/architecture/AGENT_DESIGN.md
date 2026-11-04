# Agent Design

Status: IMPLEMENTED and TESTED (mocked tests + live run against Gemini and PayPal Sandbox, 2026-11-04).

## Principle
The LLM explains and proposes. Deterministic backend code computes, validates and decides.
The agent can never execute a PayPal write operation.

## Flow
User message -> LLM -> tool call -> backend validation (allowlist + Pydantic) -> tool result
-> ... (max 6 steps, 15 tool calls) -> summary + proposed actions (awaiting approval).

## Tools (allowlist)
| Tool                 | Type     | Description                                                       |
|----------------------|----------|-------------------------------------------------------------------|
| get_invoice_analysis | Read     | PayPal invoices + deterministic analysis (state, priority, action) |
| get_invoice_details  | Read     | Analysis for one invoice ID                                       |
| propose_action       | Proposal | Records a proposal; never executes                                |

## Guardrails
- `propose_action` is accepted only when `action_type` matches the backend's `suggested_action`.
- Unknown tools, invalid JSON, extra arguments and malformed invoice IDs are rejected.
- Duplicate proposals in the same run are rejected.
- Tool results are external data; the system prompt forbids treating them as instructions.
- The final response never claims an action was executed.
- Only user-facing tool traces are returned; hidden model reasoning is never exposed.

## LLM Provider
Any OpenAI-compatible Chat Completions API (configured in `backend/.env`):
- Default: Google Gemini free tier, `gemini-3.6-flash`, `LLM_REASONING_EFFORT=low`.
- Alternative: Groq (`https://api.groq.com/openai/v1`).
- The provider's assistant message is appended unchanged so Gemini 3 thought signatures are preserved.

## Known Provider Issues (observed 2026-11-04)
- HTTP 402: API key in a Google project linked to Prepay billing with no balance. Fix: key in a new project.
- HTTP 503: `gemini-3.8-flash` overloaded on the free tier; `gemini-3.6-flash` worked.
- Diagnose with `python scripts/check_llm.py` (from backend/).
