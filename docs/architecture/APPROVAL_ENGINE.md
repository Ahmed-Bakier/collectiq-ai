# Approval & Execution Engine

Status: IMPLEMENTED (mocked tests). Enforced by the backend only.

## Endpoints
- `POST /api/actions/{id}/approve` body `{"parameters_hash": "<sha256 the user reviewed>"}`
- `POST /api/actions/{id}/reject` body `{"reason": "..."}` (optional)
- `POST /api/actions/{id}/execute`

## Rules
1. Only `pending`, unexpired actions (24h) can be approved or rejected.
2. Approval binds to the exact `parameters_hash` the user reviewed; a mismatch returns 409.
3. Rejected, expired and superseded actions can never execute.
4. Execution requires: approved status, unchanged parameter hash, approval younger than 15 minutes.
5. An atomic `not_started -> executing` update guarantees at most one execution.
6. Precondition read from PayPal: `send_invoice` needs `DRAFT`; `send_reminder` needs an open
   invoice (`SENT`, `UNPAID`, `PARTIALLY_PAID`, `SHARED`). Otherwise the execution is blocked.
7. `PayPal-Request-Id` = action ID (PayPal de-duplicates requests with the same key).
8. Verification read after execution: `send_invoice` must show a sent status.
   A reminder does not change the status; PayPal's 2xx response plus an open invoice is the evidence.
9. Timeouts after sending -> `outcome_unknown`, never retried automatically
   (unless the verification read proves a `send_invoice` was applied).
10. Every step is written to the audit trail.

## PayPal limits
- Reminders: max 2 per invoice per day (PayPal docs).
- Drafts cannot be reminded (`CANT_REMIND_INVOICE_IN_DRAFT_STATE`).
