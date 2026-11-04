# PayPal Integration

Environment: **Sandbox only** (`https://api-m.sandbox.paypal.com`).
Live mode is blocked in configuration (`paypal_environment: Literal["sandbox"]`).

## Labels
- DOCUMENTED: confirmed in official PayPal documentation, not yet called by our code.
- IMPLEMENTED: code exists with mocked tests.
- TESTED: successfully executed against PayPal Sandbox.

## Operations

| Operation        | Method + Path                                | Scope (per docs)                  | Status      |
|------------------|----------------------------------------------|-----------------------------------|-------------|
| Get access token | POST /v1/oauth2/token (client_credentials)   | —                                 | TESTED |
| List invoices    | GET /v2/invoicing/invoices                   | invoicing/invoices/read           | DOCUMENTED  |
| Show invoice     | GET /v2/invoicing/invoices/{invoice_id}      | invoicing/invoices/read           | DOCUMENTED  |
| Create draft     | POST /v2/invoicing/invoices                  | invoicing/invoices/readwrite      | DOCUMENTED  |
| Send invoice     | POST /v2/invoicing/invoices/{invoice_id}/send| invoicing/invoices/readwrite      | DOCUMENTED  |

List invoices query params (per docs): `page` (default 1), `page_size` (1–100, default 20),
`total_required`, `fields`.

## Code Layout
`backend/app/integrations/paypal/`
- `exceptions.py` — typed integration errors
- `auth.py` — OAuth token provider with in-memory caching
- `dependencies.py` — shared provider instance for FastAPI

## Security Rules
- Credentials are read from `backend/.env` only; never committed, never sent to the frontend.
- Access tokens are never logged or returned by any API endpoint.

## Sandbox Test Log
| Date       | Operation        | Result                                                   |
|------------|------------------|----------------------------------------------------------|
| 2026-11-04 | Get access token | Success via GET /api/integrations/paypal/status (connected=true) |
