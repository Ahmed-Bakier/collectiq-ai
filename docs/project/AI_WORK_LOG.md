# CollectIQ AI — AI Development Handoff

## Current Date
2026-11-04

## Current Project State
Backend (FastAPI) is connected to PayPal Sandbox: OAuth, list invoices, create draft,
send, and read-back verification all work against the real Sandbox. No frontend,
database, or AI agent yet.

## Completed Tasks
T-001 repo setup, T-002 backend skeleton, T-004 PayPal OAuth, T-005 list invoices,
T-007 create draft + send (via seed script). T-006 get invoice: adapter done, API route pending.

## Important Decisions
- PayPal Sandbox only; live mode blocked in config.
- Sandbox app must be linked to a US business account (Saudi account got no invoicing scope).
- All PayPal writes use PayPal-Request-Id; network failures on writes raise
  PayPalWriteOutcomeUnknownError and are never retried blindly.
- Project lives in ~/Projects (not iCloud-synced Desktop).

## Tests Executed
- `python -m pytest -q` (backend/, mocked HTTP): 33 passed.
- Sandbox: GET /api/integrations/paypal/status -> connected=true.
- Sandbox: seed script created 5 invoices, sent 4, verified statuses (see PAYPAL_INTEGRATION.md).
- Sandbox: GET /api/invoices -> 5 invoices.

## Known Bugs / Warnings
- StarletteDeprecationWarning about httpx in TestClient (harmless).

## Next Recommended Task
Deterministic invoice analysis service (overdue, days overdue, due soon, priority) with unit tests.
Then: LLM provider decision, agent tool registry, approval engine, database + audit log.
