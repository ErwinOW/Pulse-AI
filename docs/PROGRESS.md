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

## Known issues
- `StarletteDeprecationWarning`: Starlette suggests replacing `httpx` for its TestClient. Warning only; tests pass. Revisit before deployment — do not swap packages without checking the official Starlette changelog.

## Next actions
- First Git commit
- Frontend scaffold (React + TS + Vite)
