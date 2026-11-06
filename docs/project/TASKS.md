# CollectIQ AI — Tasks

Statuses: BACKLOG | READY | IN_PROGRESS | BLOCKED | IN_REVIEW | DONE

## Milestone 1 — Repository & Environment
| ID    | Task                                        | Priority | Status |
|-------|---------------------------------------------|----------|--------|
| T-001 | Create repo, branches, base files           | P0       | DONE   |
| T-002 | Backend skeleton (FastAPI + /api/health)    | P0       | DONE   |
| T-003 | Frontend skeleton (Vite + React + TS)       | P0       | DONE   |

## Milestone 2 — PayPal Integration (Sandbox)
| ID    | Task                                         | Priority | Status |
|-------|----------------------------------------------|----------|--------|
| T-004 | PayPal OAuth access token                    | P0       | DONE   |
| T-005 | List invoices                                | P0       | DONE   |
| T-006 | Get invoice details                          | P0       | DONE   |
| T-007 | Create draft + send invoice (needs approval) | P0       | DONE   |
| T-013 | Send payment reminder (needs approval)       | P0       | DONE   |
| T-014 | Read and record payments (payment history)   | P1       | DONE   |

## Milestone 3 — Backend Foundation
| ID    | Task                                                  | Priority | Status |
|-------|-------------------------------------------------------|----------|--------|
| T-008 | Database models (create_all; Alembic deferred)        | P0       | DONE   |
| T-009 | Invoice analysis service (overdue/priority)           | P0       | DONE   |
| T-010 | Approval engine + audit log                           | P0       | DONE   |
| T-015 | Edit and AI rewrite create new versions               | P1       | DONE   |

## Milestone 4 — AI Agent
| ID    | Task                                                  | Priority | Status |
|-------|-------------------------------------------------------|----------|--------|
| T-011 | Choose AI provider + tool registry                    | P0       | DONE   |
| T-012 | Agent run with structured action plan                 | P0       | DONE   |
| T-016 | Client insights tool + risk-aware tone                | P1       | DONE   |
| T-017 | Reminder cooldown in the agent                        | P1       | DONE   |
| T-018 | Fallback model on rate limits / provider errors       | P1       | DONE   |

## Milestone 5 — Product Features
| ID    | Task                                                  | Priority | Status |
|-------|-------------------------------------------------------|----------|--------|
| T-019 | Collection Autopilot (playbook, policy, kill switch)  | P1       | DONE   |
| T-020 | Client payment intelligence + 30-day forecast         | P1       | DONE   |
| T-021 | Message safety check + Safety & trust page            | P1       | DONE   |
| T-022 | Red-team prompt-injection test and Sandbox script     | P1       | DONE   |

## Milestone 6 — Frontend
| ID    | Task                                                         | Priority | Status |
|-------|--------------------------------------------------------------|----------|--------|
| T-023 | Dashboard, AI Assistant, Approvals, Activity Log             | P0       | DONE   |
| T-024 | Invoices page with AG Grid                                   | P1       | DONE   |
| T-025 | Autopilot, Clients and Safety pages; forecast chart          | P1       | DONE   |

## Milestone 7 — QA, Deployment & Submission
| ID    | Task                                                         | Priority | Status      |
|-------|--------------------------------------------------------------|----------|-------------|
| T-026 | Backend tests (111) + frontend lint/build                    | P0       | DONE        |
| T-027 | Docker + Render deployment (live demo)                       | P0       | DONE        |
| T-028 | README, CHANGELOG, Postman collection                        | P0       | IN_REVIEW   |
| T-029 | Demo video (< 3 min, YouTube)                                | P0       | READY       |
| T-030 | Secret scan, public repo, license in About                   | P0       | READY       |
| T-031 | Merge to main, Render on main, Devpost submission            | P0       | READY       |
