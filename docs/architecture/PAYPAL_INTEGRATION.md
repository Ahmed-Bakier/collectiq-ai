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
| List invoices    | GET /v2/invoicing/invoices                   | invoicing/invoices/read           | TESTED  |
| Show invoice     | GET /v2/invoicing/invoices/{invoice_id}      | invoicing/invoices/read           | TESTED  |
| Create draft     | POST /v2/invoicing/invoices                  | invoicing/invoices/readwrite      | TESTED  |
| Send invoice     | POST /v2/invoicing/invoices/{invoice_id}/send| invoicing/invoices/readwrite      | TESTED  |
| Send reminder    | POST /v2/invoicing/invoices/{invoice_id}/remind | invoicing/invoices/readwrite | IMPLEMENTED |

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
| 2026-11-04 | List invoices    | 403 NOT_AUTHORIZED with an app linked to a Saudi Arabia sandbox business account |
| 2026-11-04 | List invoices    | Success via GET /api/invoices with a US sandbox business account (0 invoices) |

## Known Limitations
- An app linked to a **Saudi Arabia** sandbox business account was not granted the
  `https://uri.paypal.com/services/invoicing` scope, and invoice calls returned
  `403 NOT_AUTHORIZED`. An app linked to a **United States** sandbox business account
  received the scope and worked. Invoicing availability appears to depend on the
  account country (observed behavior, not confirmed in official docs).
- To diagnose granted scopes without exposing the token, run from `backend/`:
  `python scripts/check_paypal_scopes.py`

## Sandbox Seed Run (2026-11-04)
Created via `python scripts/seed_sandbox_invoices.py --execute` (each step verified by GET):

| Invoice ID               | Client             | Amount   | Due date   | Status |
|--------------------------|--------------------|----------|------------|--------|
| INV2-7RCD-EG9Z-UPDV-3WMR | Acme Design Studio | 1200 USD | 2026-11-05 | SENT   |
| INV2-3U7H-DN6D-QQQX-XGHT | Northwind Traders  | 450 USD  | 2026-11-06 | SENT   |
| INV2-Z9J9-HB6F-L85F-SM88 | Blue Harbor Cafe   | 780 USD  | 2026-11-09 | SENT   |
| INV2-KL43-79TF-MF6Z-VPG3 | Lumen Analytics    | 2350 USD | 2026-11-18 | SENT   |
| INV2-8NXM-5NKL-3XLX-NSFD | Pixel & Co         | 300 USD  | 2026-11-11 | DRAFT  |

Observations:
- After sending, PayPal reports status `SENT` (not `UNPAID`).
- The list response includes `payment_term.due_date` but not `term_type`.
- PayPal docs require invoice/due dates of today or later, so overdue demo data
  is produced by short due dates that age naturally.

## Approval Flow Live Test (2026-11-04)
Agent proposal e2ab4f64-c348-432b-a04b-5e58e7780fe0 (send_invoice, Pixel & Co, 300 USD)
-> approved with parameters hash 4fad54eb... -> executed with PayPal-Request-Id = action ID
-> verification read: DRAFT -> SENT (verified). Full audit trail recorded.
