# CollectIQ AI — AI Development Handoff

## Current Date
2026-11-04

## Current Project State
Backend (FastAPI) is connected to PayPal Sandbox and to Google Gemini (free tier).
The AI agent analyzes real Sandbox invoices and proposes actions that await approval.
Not yet built: approval/execution engine, database + audit log, frontend, deployment.

## Completed Tasks
T-001, T-002, T-004, T-005, T-007, T-009, T-011, T-012. T-006 (get invoice) adapter only.

## Important Decisions
- PayPal Sandbox only; US sandbox business account (Saudi account had no invoicing scope).
- PayPal writes use PayPal-Request-Id; ambiguous write failures are never retried blindly.
- Deterministic analysis decides overdue status, priority and allowed actions; the LLM never does.
- LLM via OpenAI-compatible API (Gemini default, Groq alternative); model gemini-3.6-flash.
- Project lives in ~/Projects (not iCloud-synced Desktop).

## Tests Executed
- `python -m pytest -q` (backend/, mocked HTTP and fake LLM): 60 passed.
- Live: GET /api/invoices/analysis on 5 Sandbox invoices (values verified by hand).
- Live: POST /api/agent/runs -> analysis tool call + send_invoice proposal for the draft invoice.

## Known Issues
- Free-tier Gemini models can return 503 when overloaded (no automatic fallback yet).
- StarletteDeprecationWarning about httpx in TestClient (harmless).

## Next Recommended Task
Approval + execution engine with SQLite persistence and audit log:
approve/reject endpoints, exact-parameter binding, expiry, single execution,
PayPal send_invoice execution with verification. Verify the PayPal reminder endpoint first.
