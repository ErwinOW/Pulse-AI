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
| AI | Microsoft Agent Framework + **Google Gemini free tier** (no card) | GitHub Models retired 2026-07-30; Azure declined (card required). Groq only if Gemini limits are hit. LLM never computes stats |
| Hosting | Free, no-card host (TBD at deploy time) | Azure declined |
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
- [x] 1.1 Event schema (`backend/app/schema/`) — 11 event types, match consistency checks — **26 passed**; commit `0e0f9ed`
- [x] 1.2 Phase-based simulator + demo/balanced scenarios + ground truth — **43 passed**; commit `550bf7c`
- [x] 2.1 Statistics engine (`backend/app/stats/`): turnovers, possession share, pass %, shots, box entries, pressure rates, momentum, rolling windows — **64 passed**; commit `a792954`
- [x] 2.2 Realism fixes (restarts, final-third circulation, shot chance, outside→inside box entries) — **69 passed**; commit `c432a39`. Demo now: 1,717 events, goals NBR 35' / EAS 64', shots 17 / 16

## Known issues
- Detector (v2) false alerts: ~0.4 per no-shift match; can fire on a short intense pressing burst. Small 5-minute counts limit what fixed thresholds can separate. UI should show confidence + sample notes; README must quote the seeds 300–309 numbers.
- Balanced fixture (seed 7) is uneven for one match (possession 56/44, shots 21 vs 12); 20-seed test shows no systematic bias. Kept to avoid cherry-picking; simulator possessions are streakier than real football.
- ~~`StarletteDeprecationWarning` (httpx → httpx2)~~ — resolved 2026-10-19: `httpx2` arrived as a dependency of the `openai` SDK; warning no longer shown.

## Notes
- In dev, `/api/health` is requested twice per page load: React StrictMode intentionally runs effects twice in development only.
- npm 12 is available; staying on npm 11.19.1 until after the hackathon.

- [x] 2.3 Pressing-increase detector (`backend/app/detection/`) — **default v2**; final results on fresh seeds 300–309: planted press detected **9/10** (mostly 55'–63'); **6 false alerts in 10 demo-scenario matches** (3 during the 20'–23' burst); **4 false alerts in 10 no-shift matches** (0.4/match). Fixed demo seed 42: 1 alert at 62', 0 false. Shortfalls kept as `xfail(strict=True)` tests.
  - v1 ("any 2 of 3 signals", 2-min persistence) on seeds 100–109: detected 9/10 planted presses, but **25 false alerts in 10 balanced matches** and 20 in 10 demo-scenario matches; also alerted on the 22' false-alarm burst. Cause: S2/S3 double-count the same lost balls; 2 min shorter than the burst.
  - v2: S1 required AND (S2 or S3); 4-min persistence. Held-out seeds 200–209: **6/10 detected, 4 false alerts (balanced), 5 (demo)** — missed targets. Fixed demo seed 42: 1 alert at 62', 0 false. Fixed balanced seed 7: 2 false.
  - v3: S1 = one-sided conditional binomial rate test (p < 0.01) instead of fixed ratio. Decision rule fixed in advance: v3 replaces v2 only if it has fewer total errors on fresh seeds 300–309 AND gets the fixed demo exactly right. Result: v3 7/10 detected, 3 false alerts total (6 errors) vs v2 9/10, 10 false (11 errors) — but v3 **missed the fixed demo**, so **v2 kept**. v3 remains in code (`V3_RATE_TEST`) as a documented, more conservative alternative. Tuning closed.

- [x] 3.1–3.2 Gemini (`gemini-3.5-flash-lite`) via Agent Framework `OpenAIChatCompletionClient` — live check 1.57 s, EN + ID output; commit `eb32113`
- [x] 3.3 Narrative core (`backend/app/narrative/`): fact sheets, `Narrative` schema, deterministic evidence validator (numbers, event ids, confidence, causal wording EN/ID, hypotheticals, ID decimal comma), EN/ID × casual/analyst fallbacks — **98 passed, 3 xfailed**
- [x] 3.4 Storyteller (Agent Framework `Agent`, schema / prompt-JSON modes) + generate→validate→retry→fallback pipeline — **108 passed**; commit `282be8a`
- [ ] 3.5 Live run (gemini-3.5-flash-lite, schema mode works): 4/4 AI-written on first attempt, but review found validator v1 gaps — causal phrasings ("made it much harder", "hal ini membuat", "merespons") and an English text with decimal commas. Fixed in validator v2 + prompt v2; re-run pending.

## Repository
GitHub: https://github.com/ErwinOW/Pulse-AI (pushed 2026-10-18). **Must be public before submission** — check by Oct 26.

## Next actions (resume here)
- Approve + build pressing-increase detector (design proposed 2026-10-17: 2-of-3 signals, 5-min recent vs 15-min baseline, 2 consecutive minutes, dedup; evaluate on 10 extra seeds per scenario)
- Phase 3 status (2026-10-18): Gemini key works (`scripts/list_gemini_models.py` → 63 models); `.env` confirmed git-ignored; installed agent-framework-core 1.22.0 + agent-framework-openai 1.17.0 (openai 3.35.1, httpx2). Model chosen: `models/gemini-3.5-flash-lite`.
- **Resume here:** run `python -m scripts.check_llm` (first live call, untested), refresh `requirements.lock`, run pytest (check whether the Starlette/httpx warning changed), user reviews Indonesian sentence quality, then commit. Then propose the AI layer design.
- Note: without Azure, Foundry / Azure Cloud Native category prizes are out of reach; Agent Framework is the Microsoft hero technology
