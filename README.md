# CollectIQ AI

> AI-powered invoice collection agent for freelancers and small businesses, built on PayPal.

**Status:** 🚧 Work in progress — built for the "Build What's Next with PayPal and AI" hackathon.

## Overview

CollectIQ AI helps freelancers and small agencies analyze unpaid PayPal invoices,
prioritize collection work, and execute approved actions through the PayPal Invoicing API.
Every external write operation requires explicit human approval, and every step is recorded
in a transparent audit trail.

## Core Workflow

1. The user asks the agent in natural language (e.g. "Which invoices need attention this week?").
2. The agent reads invoice data from PayPal (Sandbox).
3. Deterministic analysis detects overdue invoices and calculates priority.
4. The agent proposes a structured action plan.
5. The user approves or rejects each action.
6. The backend executes approved actions through PayPal and verifies the result.
7. Every step is written to the audit log.

## Tech Stack (planned)

| Layer    | Technology                                         |
|----------|----------------------------------------------------|
| Frontend | React, TypeScript, Vite, Tailwind CSS, shadcn/ui   |
| Backend  | Python 3.12, FastAPI, Pydantic, SQLAlchemy         |
| Database | SQLite (local), PostgreSQL (deployed)              |
| Payments | PayPal Invoicing REST API v2 (Sandbox)             |
| AI       | To be decided                                      |

## Project Structure

```
collectiq-ai/
├── backend/    # FastAPI application
├── frontend/   # React application
└── docs/       # Project documentation
```

## Getting Started

Setup instructions will be added as each component is implemented.

## License

MIT — see [LICENSE](LICENSE).