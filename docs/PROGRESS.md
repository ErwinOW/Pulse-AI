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
- Opening goal in the demo has no recorded ball win (scripted patient build-up starts right after an EAS interception); turning points report `possession_start: "not_recorded"` instead of guessing. Fixing it means regenerating fixtures — not done.
- New terminals need the venv: `C:\dev\pulse\backend\.venv\Scripts\Activate.ps1` (else "No module named pytest").
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
- [x] 3.5 Live run (gemini-3.5-flash-lite, schema mode): review found validator gaps (causal phrasings, decimal commas in English, "21.0" counts, English terms leaking into Indonesian); fixed across validator v2 + prompts v2–v4. 4 validated AI insights (EN/ID × casual/analyst) cached in `data/narratives/cache.json`, prompt v4 — **122 passed, 3 xfailed**; commit `c3e2af0`
- [x] 4a.1 API: fixture loading, `GET /api/matches`, `/api/matches/{id}`, `/api/matches/{id}/state?t=`, `/api/definitions`; state uses only events before t (alerts/momentum per completed minute, cached) — **131 passed, 3 xfailed**; commit `ed9ce71`
- [x] 4a.2 Turning points: `GET /api/matches/{id}/turning-points?t=` — per goal: possession traced back, turnover (under pressure?) when recorded, scoring team's pressures, score before/after, alerts confirmed within 10 min before (timing link only) — **137 passed, 3 xfailed**; commit `5b2c4dc`
- [x] 4a.3 Insight endpoints: `GET /api/matches/{id}/insights/{alert_id}?audience=&language=&t=` (cached validated AI or labelled fallback, never calls the model; 404 before the alert is raised) + `POST .../regenerate` (one at a time → 429, 20/day cap → 429, no key → 503; in-memory unless `PULSE_SAVE_CACHE=1`). Insights now use **detection-time facts** (the end-of-match alert version mentioned 70' confirmations → future leak during replay); cache regenerated with `run_live_insights --save --fresh`: 4/4 AI on first attempt, 2.6–3.1 s each — **148 passed, 3 xfailed**; commit `9d6eb26`
- [x] 4a.4 `WS /api/matches/{id}/replay?speed=1-60&from=` — control / tick (only new events + new alerts, clock, score) / end / error messages; client commands pause, play, seek, speed; frontend falls back to polling `/state?t=` if a host blocks WebSockets — **154 passed, 3 xfailed** (2026-10-20). **Backend API complete.**; commit `ed44e9d`
- [x] 5.0 Hosting: Render free web service (no card asked), Blueprint `render.yaml` + `.python-version` 3.13; live at **https://pulse-k9mh.onrender.com** — health, matches, state, turning points, cached insight, WebSocket replay all verified 2026-10-20 (commit `43f9bbf`). Free plan: sleeps after 15 min idle, ~1 min wake. Replay ticks ~0.6 s instead of 0.25 s on the free CPU (precompute minute products at startup — deferred). Plan B: static GitHub Pages.
- [x] 6.1 Dashboard step 1: API types/client, `useReplay` (WebSocket + polling fallback, starts paused), page frame (score, clock, controls, audience/language/match pickers). Key-event labels (user request: show meaningful events, not every pass): `app/stats/key_events.py` — goal, shot, key_pass, box_entry, ball_won_high, lost_under_pressure, winning_press, foul, substitution, period; each label has `revealed_s` (no future); ~15% of events. `/state` sends `key_events` + `event_tags`, ticks send `new_tags`. Feed defaults to Key events with All events toggle; verified in browser — **161 passed, 3 xfailed**, lint + build clean; commit `a3e094f` (2026-10-20)
- [x] 6.2 Momentum chart (Recharts): diverging bars per minute (home above / away below the middle line, user's request), alert window shaded, goal markers; `/state` sends `goals`; commit `66c0998`
- [x] 6.3 Insight card: cached/fallback text per audience + language, source labels, evidence table (before vs now + counts) and cited events (`evidence_events` in insight API), regenerate with busy/limit messages — **162 passed, 3 xfailed**; commit `1ea322f`
- [x] 6.4 Turning points panel, full EN/ID UI strings (`src/i18n.ts`, `<html lang>`), two-row controls (wide timeline), phone layout; checked EN + ID + mobile in browser (2026-10-21)
- [x] 6.5 Casual vs analyst made distinct (user feedback): prompt **v5** (casual = fan language, at most 2 event totals, no rates/%) enforced by a new validator rule; casual fallback rewritten to match; analyst gets a Numbers panel (last 5 min vs match), y-axis values, pitch thirds in the feed, evidence open by default. Cache regenerated: 4/4 AI first attempt. Known weakness kept: casual/en summary has a hedged guess ("might have unsettled") the validator's causal list does not cover — **163 passed, 3 xfailed**; commit `db92d4f`
- [x] 6.6 Whole app live as ONE Render service (user chose the simpler option): FastAPI serves `frontend/dist` at `/`; Render builds frontend + backend from the repo root (no rootDir). Render service settings had to be fixed by hand (start command kept the old value after the push; Blueprint sync is partial) — **165 passed, 3 xfailed**; commit `7895b62`. Verified live 2026-10-21: page, live stream (WSS), seek, chart, cached v5 insight EN/ID, turning points, playback ~10x.

## Repository
GitHub: https://github.com/ErwinOW/Pulse-AI (pushed 2026-10-18). **Must be public before submission** — check by Oct 26.

## Next actions (resume here)
- Judges' link: **https://pulse-k9mh.onrender.com** (free plan: ~1 min blank page if asleep).
- README (what it does, architecture, agent design, measured detector numbers + limitations, how to run), architecture diagram, demo video < 2 min; make repo public by Oct 26; submit by Oct 27 23:59 PT.
- Optional: keep-alive ping during judging, replay speed fix, Render settings must stay in sync with render.yaml (check Settings after editing it).
- User to review Indonesian UI wording (src/i18n.ts).
- Note: without Azure, Foundry / Azure Cloud Native category prizes are out of reach; Agent Framework is the Microsoft hero technology
