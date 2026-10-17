# PULSE — Progress Log

Single source of truth for decisions, environment, completed steps, and known issues.
Specification: [`PULSE_Project_Brief.md`](../PULSE_Project_Brief.md)

## Key dates (Pacific Time)
| Date | Milestone |
|---|---|
| 2026-10-20 12:00 | Registration closes (done ✅) |
| 2026-10-27 23:59 | Submission deadline |
| 2026-11-10 | Test link must remain live until end of judging |

## Hackathon rule constraints
- Data **must be synthetic** and football-realistic (no real feeds such as StatsBomb).
- Public GitHub repo, demo video **< 2 minutes**, free public test link.
- Judged on 5 × 20%: Technological Implementation, Agentic Design & Innovation, Real-World Impact, UX & Presentation, Category Adherence.
- Challenge text asks for multi-language storytelling → English + Indonesian.

## Approved decisions
| Area | Choice | Notes |
|---|---|---|
| Backend | Python 3.13 + FastAPI + Pydantic | 3.13 kept (already installed) |
| Tests | pytest | |
| Frontend | React + TypeScript + Vite + Recharts | |
| Streaming | WebSocket timed replay | |
| Storage | JSON fixtures | SQLite only if needed |
| AI | Microsoft Agent Framework; GitHub Models (dev), Azure Foundry (demo) | Added day 5; LLM never computes stats |
| Hosting | Azure free account | |
| Languages | English, Indonesian | |
| Budget | ≈ $10 | |
| Scope | P0 only; Feature G / counterfactuals / tactical pitch cut unless ahead on Oct 24 | Recap is first add-back |

## Environment
Windows 11 · Python 3.13.16 · Node 24.22.0 · npm 11.19.1 · Git 2.55.0 · VS Code 1.142.0
PowerShell execution policy: CurrentUser = RemoteSigned (needed for npm.ps1 and venv activation).

Backend packages (exact versions in `backend/requirements.lock`):
fastapi 0.143.3 · uvicorn 0.54.0 · pydantic 2.14.1 · pytest 9.1.1 · httpx 0.28.1

## Completed steps
- [x] 0.1 Tool check
- [x] 0.2–0.3 Execution policy fixed
- [x] 0.4 Repo created at `C:\dev\pulse` (branch `main`)
- [x] 0.5 Backend venv + core packages
- [x] 0.6 Health endpoint + first test — **1 passed** (2026-10-17)
- [x] 0.7 First commit `03004f3`; `.gitattributes` added to normalize line endings (LF)
- [x] 0.8 Frontend scaffold: create-vite 9.2.1, React 19, TypeScript 6, Vite 8.3.4, ESLint 10 — build OK, 0 vulnerabilities
- [x] 0.9 Vite `/api` proxy → FastAPI; status page shows "Backend connected" (backend logged `GET /api/health 200`)

## Known issues
- `StarletteDeprecationWarning`: Starlette suggests replacing `httpx` for its TestClient. Warning only; tests pass. Revisit before deployment — do not swap packages without checking the official Starlette changelog.

- [x] 1.1 Event schema (`backend/app/schema/`) — 11 event types, match consistency checks — **26 passed** (2026-10-17)
- [x] 1.2 Phase-based simulator + demo/balanced scenarios + ground truth — **43 passed**; demo 1,540 events, goals NBR 34' / EAS 63'; commit `550bf7c`
- [x] 2.1 Statistics engine (`backend/app/stats/`): turnovers, possession share, pass %, shots, box entries, pressure rates, momentum, rolling windows — **64 passed**

## Notes
- In dev, `/api/health` is requested twice per page load: React StrictMode intentionally runs effects twice in development only.
- npm 12 is available; staying on npm 11.19.1 until after the hackathon.

## Next actions
- Verify simulator tests; inspect generated demo match
- Phase 2: statistics engine
