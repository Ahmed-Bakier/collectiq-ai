# Data Model

PayPal is the source of truth for invoices. The database only stores what CollectIQ
proposed, what the user decided, and what was executed and verified.

## Tables
| Table        | Purpose                                                                 |
|--------------|-------------------------------------------------------------------------|
| agent_runs   | User request, agent summary, model, tool-call trace                     |
| actions      | Proposed actions with exact PayPal parameters and their SHA-256 hash    |
| audit_events | Append-only timeline: who (user/agent/system) did what, when, on what   |

## Action lifecycle (tracked separately)
- approval_status: pending -> approved | rejected | expired | superseded
- execution_status: not_started -> executing -> succeeded | failed | outcome_unknown
- verification_status: not_verified -> verified | mismatch

Rules:
- Approval window: 24 hours after the proposal; then `expired` (applied on read).
- A new proposal for the same invoice and action type supersedes the pending one.
- Approval binds to `parameters_hash`; execution must match the approved hash.

## Decisions
- SQLite locally (`sqlite:///./collectiq.db`, async via aiosqlite); PostgreSQL URLs are
  mapped to asyncpg for deployment.
- Tables are created at startup with `create_all`. Alembic migrations are DEFERRED until
  after the hackathon MVP (no production data yet).
- All timestamps are stored and returned as UTC.
