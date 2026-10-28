# TRAFIQON

Transportation optimization and simulation workbench: directed CVRP on a road graph, dynamic traffic, incident replanning, and a QPSO-inspired discrete optimizer compared against OR-Tools and Simulated Annealing.

## How to work (read first, every session)
1. Read `STATUS.md` before doing anything. Update it before you stop.
2. Work on ONE milestone at a time. Read only the docs that milestone needs (see the table below). Stop at the milestone's end and report.
3. Inspect the repo before changing it. Preserve existing work.
4. Vertical slice first. Tests come with the code, not after.
5. Run the real test and lint commands. Report actual output. Never claim a pass you did not see.
6. If a requirement is infeasible or ambiguous, stop, explain, propose a fix, and record it in `STATUS.md` under Decisions. Never silently weaken it.

## Hard rules
- No fabricated metrics, progress, events, or benchmark results. Show measured data only.
- No placeholder or random-search stand-in for a required algorithm.
- Never claim quantum hardware or quantum speedup. Never claim equivalence to canonical QPSO unless implemented.
- Core logic (domain, routing, optimization, simulation) has no dependency on FastAPI, SQLAlchemy, Celery, Redis, or React.
- One authoritative objective evaluator shared by all algorithms.
- Backend is authoritative for scenarios, runs, and simulation state. Frontend only renders and interpolates.
- No microservices, Kubernetes, or paid APIs.
- Unreachable legs are reported as infeasible, never given an arbitrary large cost and passed off as valid.
- Terminal run states never get overwritten (a cancelled run cannot become COMPLETED).

## Stack
Backend: Python, uv, FastAPI, Pydantic, SQLAlchemy 2, Alembic, NumPy, NetworkX, OR-Tools, pytest, Ruff.
Worker: a separate worker process (not threads in the API) consuming a Postgres-backed job queue (`SELECT ... FOR UPDATE SKIP LOCKED`) behind a `JobQueue` interface. Celery + Redis is DEFERRED (see STATUS.md Decisions); it may be added after M8 as another `JobQueue` implementation. DB: PostgreSQL (JSONB only for variable config/metrics). Progress via SSE from `run_events`.
Frontend: Next.js App Router, strict TS, Tailwind, shadcn/ui, React Flow, Zustand, TanStack Query, ECharts, Vitest, Playwright, npm.
Delivery: Docker Compose, GitHub Actions, `.env.example`.

If Docker or Postgres cannot run in this environment, say so, keep the code behind interfaces, run what can run (SQLite or an in-process worker for local tests only; the Postgres queue's SKIP LOCKED behaviour must be tested on real Postgres), and mark the integration tests as not run.

## Layout
```
backend/src/trafiqon/{domain,routing,optimization,simulation,experiments,worker,persistence,api}
backend/tests/
frontend/            # Next.js app
docs/                # SPEC.md, DESIGN.md, PROMPTS.md, then docs written during the build
STATUS.md
```
Adapt to the existing repo, but keep these logical boundaries.

## Source of truth
`docs/SPEC_FULL.md` is the complete original specification and wins over every other doc. `docs/SPEC.md` and `docs/DESIGN.md` are condensed working summaries. Before finishing a milestone, re-read the matching sections of `docs/SPEC_FULL.md` (milestone list in section 19, Definition of Done in section 20) and check your work against them, not just the summaries. If they disagree, follow SPEC_FULL.md and note it in STATUS.md. Exception: a deviation recorded under Decisions in STATUS.md (currently: Postgres-backed queue instead of Celery + Redis) overrides SPEC_FULL.md for that point only.

## Which doc to read
| Milestone | Read (summary; then verify against `SPEC_FULL.md`) |
|---|---|
| 0 Plan | `docs/SPEC.md` sections 1-4 |
| 1 Domain + routing | `docs/SPEC.md` section 1 |
| 2 Baselines | `docs/SPEC.md` sections 2-3 |
| 3 QPSO optimizer | `docs/SPEC.md` section 3.4 |
| 4 Persistence, API, worker | `docs/SPEC.md` sections 5-6 |
| 5-6 Frontend | `docs/DESIGN.md` + `docs/SPEC.md` section 8 |
| 7 Simulation | `docs/SPEC.md` section 4 |
| 8 Hardening + docs | `docs/SPEC.md` sections 7, 9 |

## Commands (fill in as they are established)
- Backend test: `cd backend && uv run pytest` (integration tests need Postgres: `docker compose up -d db` and `trafiqon_test` DB; they skip, i.e. NOT RUN, if unreachable)
- Migrations: `cd backend && TRAFIQON_DATABASE_URL=... uv run alembic upgrade head`
- Backend lint: `cd backend && uv run ruff check . && uv run ruff format --check .`
- Frontend test: `cd frontend && npm test`
- Frontend lint/build: `cd frontend && npm run lint && npm run build`
- API dev server: `cd backend && TRAFIQON_DATABASE_URL=... uv run uvicorn trafiqon.api.app:app --port 8000`
- Worker: `cd backend && TRAFIQON_DATABASE_URL=... uv run python -m trafiqon.worker.main [--migrate]`
- Web dev server: `cd frontend && npm run dev` (API URL from `NEXT_PUBLIC_API_BASE_URL`, default http://localhost:8000)
- E2E: `cd frontend && npx playwright test`
- Stack: `docker compose up` (M4: `db` service only; api/worker/web services come in M8)

## End-of-milestone report format
Implemented / commands actually run / actual results / known defects / decisions / next milestone + acceptance criteria.
