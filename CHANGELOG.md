# Changelog

All notable changes to CollectIQ AI. Dates are in 2026.

## [1.0.0] - 2026-11-06

First complete release for the "Build What's Next with PayPal and AI" hackathon.

### Deployment and reliability (PR #21)
- LLM fallback model: one retry on a second model on rate limits or provider errors.
- Per-visitor rate limit on AI requests for the public demo.
- The backend serves the built React app (single origin, client-side routes).
- Multi-stage Dockerfile and Render blueprint; live demo on Render.

### Safety (PR #19, #20)
- Deterministic message safety check on every AI-written client message: payment redirection, links, email addresses, threats, invented charges, injected instructions, placeholders.
- Unsafe agent proposals are rejected with the reason; unsafe autopilot drafts fall back to templates and are audited (`ai_output_blocked`).
- Agent reminder cooldown: no reminder within 3 days of the previous one.
- Safety report (`GET /api/safety`) with live evidence from the audit trail, on-demand message check, and the Safety & trust page.
- Red-team Sandbox script with a prompt-injection attempt in the client name.

### Client payment intelligence (PR #16, #17, #18)
- Payment dates read from PayPal; per-client on-time rate, average days late and explainable risk level.
- 30-day collections forecast with weekly buckets and at-risk amounts (`GET /api/insights`).
- Agent tool `get_client_insights`; risk-aware tone for high-risk overdue clients.
- Dashboard forecast chart, Clients to watch, Autopilot card, and the Clients page.
- Sandbox script that records realistic paid history (`POST /v2/invoicing/invoices/{id}/payments`).

### Collection Autopilot (PR #14 and follow-up)
- Deterministic playbook (action, tone ladder, skips for pending proposals and reminder cooldown).
- AI drafts messages with template fallback.
- Strict auto-approve policy (off by default), kill switch, optional schedule; Autopilot page.

### Approvals and editing (PR #11, #12)
- Edit a proposal or rewrite it with AI in another tone or language; every change creates a new version that needs a new approval.

### Invoices (PR #13)
- AG Grid invoices table with filters, search, CSV export and "ask the agent" per row (lazy-loaded).

### Foundation (PR #1 to #10)
- PayPal OAuth, invoice listing, send and remind; deterministic invoice analysis.
- Gemini agent with allowlisted tools and proposals only.
- SQLite persistence and append-only audit trail.
- Approval engine: SHA-256 parameter hash, 24-hour approval window, atomic execute-once, PayPal precondition and verification reads, `PayPal-Request-Id` idempotency, outcome-unknown handling.
- React app: Dashboard, AI Assistant, Approvals, Activity Log, Integrations.
