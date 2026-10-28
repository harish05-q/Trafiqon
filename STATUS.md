# TRAFIQON Status

Update this file at the end of every work session. It is the source of truth after a context reset.

## Current milestone
M1 done (2026-10-28). Next: M1.5 thin vertical slice (D2). Nothing committed yet (git repo initialised, no commits).

## Milestones
| # | Name | State | Acceptance criteria met |
|---|---|---|---|
| 0 | Inspect and plan | done | Inventory, structure, conflicts, infra findings, plan, risks, slice reported (2026-10-28) |
| 1 | Domain + routing (Dijkstra, A*) | done | All M1 criteria below; 93 tests, ruff clean (2026-10-28) |
| 1.5 | Thin vertical slice (D2) | todo | |
| 2 | OR-Tools + SA + common interface | todo | |
| 3 | QPSO-inspired optimizer | todo | |
| 4 | Persistence, API, worker | todo | |
| 5 | Frontend foundation + design system | todo | |
| 6 | Four workspaces end to end | todo | |
| 7 | Simulation + replanning | todo | |
| 8 | Hardening, benchmarks, docs | todo | |

### Acceptance criteria (from M0 plan)
- M1: uv project + ruff + pytest; Graph/Edge/Scenario models with validation (direction, closures, depots, demands, capacity); Dijkstra + A* (A* cost == Dijkstra on all fixtures + random-graph property test); path reconstruction; cost matrix keeping leg paths with explicit unreachable markers; ONE evaluator (exactly-once coverage, capacity, depot start/end, open edges, reachability) returning objective + violations; 3 deterministic fixtures (urban_grid, congested_city, incident_response); import-boundary test (core imports no FastAPI/SQLAlchemy). Ruff check/format + pytest pass, output recorded here.
- M1.5: FastAPI `GET /api/v1/health`, `GET /api/v1/scenarios/builtin`, `POST /api/v1/routing/shortest-path` (fixtures only, no DB, evaluator output); minimal Next.js page drawing scenario + returned path in React Flow. TestClient API test, one Vitest test, check drawn path == API path.
- M2: common contract (seed, progress cb, cancel token, history, termination reason, diagnostics); OR-Tools on directed matrix (unreachable -> infeasible, no big-M; never "optimal" unless proven); real SA. Both re-scored by shared evaluator; determinism, cancellation, infeasible-scenario tests.
- M3: `docs/algorithms.md` first; random-key encoding, decode, repair, pbest/gbest, mean-best attractor update with contraction-expansion beta, discrete operators. Decode/update/repair tests, determinism, cancellation, evaluator parity, documented limitations, no canonical-QPSO claim.
- M4: Alembic from clean DB; immutable scenario versions, runs, run_events, results; JobQueue + PostgresJobQueue + worker process + heartbeat + stale recovery; SSE; cancel; idempotent submit. Integration tests on real Postgres (SKIP LOCKED, cancel race, worker exception, terminal immutability), else marked not run.
- M5: tokens (dark + warm light), shell, panels, React Flow renderer, TanStack Query on real API. ESLint + Prettier, build, Vitest pass.
- M6: four workspaces on real endpoints. Playwright E2E 1-4.
- M7: deterministic engine, edge traversal, incidents, replan preserving positions/completed stops. Unit tests + E2E 5.
- M8: benchmarks/exports from stored results, a11y, perf, docs review, Compose + CI. Full suite + build; E2E 6; SPEC_FULL section 20 walked.

## Decisions
(date, decision, reason)
- D1 (2026-10-28): Use a Postgres-backed job queue (`SELECT ... FOR UPDATE SKIP LOCKED`) with a separate worker process behind a `JobQueue` interface, instead of Celery + Redis. Reason: Celery/Redis add the most setup and integration-test friction and nothing in M1-M8 needs them; the DB row is the durable queue entry, so no outbox is required. Deviates from SPEC_FULL.md sections on Background processing and Milestone 4 / Definition of Done ("Celery tasks and Redis configuration"). Cost: polling latency; Celery + Redis is a commonly expected stack. Plan: optionally add `CeleryJobQueue` after M8. Do not describe the system as using Celery or Redis in docs until that exists.
- D2 (2026-10-28): Add M1.5, a thin vertical slice (fixtures-only API + one React Flow page), after M1 and before M2. Reason: SPEC_FULL section 21 requires the first slice to reach API + React Flow, while CLAUDE.md requires one milestone at a time and M1 is core-only. M4/M5 later replace the slice's scaffolding with the real persistence and design system.
- D3 (2026-10-28): Keep directory `frontend/` for SPEC_FULL section 5's `web` module. Add Prettier (`prettier --check`) to frontend lint in M5, as SPEC_FULL section 4 requires and CLAUDE.md's command list omits.
- D5 (2026-10-28): The shared evaluator lives in `routing/evaluation.py` (SPEC_FULL section 5: "routing: shortest-path algorithms and route evaluation"), not `domain/`, because it needs shortest paths. Core entities are frozen dataclasses (Pydantic stays at the API boundary). NetworkX is a dev dependency, used only as a test oracle.
- D6 (2026-10-28): Modelling rules: integer demands/capacities (OR-Tools-friendly); customers may not sit on depot nodes; a vehicle starts at its start depot and ends at one of `end_depot_ids` (default: its start depot); the evaluator still reports `objective` for capacity- or coverage-violating solutions (with `feasible=False`), but `objective=None` whenever any leg is unreachable or invalid.
- D4 (2026-10-28): Docker Compose uses `postgres:18`, matching the locally installed PostgreSQL 18.1 binaries. Worker uses sync SQLAlchemy/psycopg to avoid Windows asyncio event-loop issues with psycopg async.

## Assumptions and risks
1. Discrete QPSO justification: the mean-best update needs a latent (random-key) space with a precisely defined decode; must show the update contributes (ablation vs local search only) or stop and document.
2. Feasibility: capacity repair and unreachable legs on directed graphs with closures; the shared evaluator is the only feasibility gate.
3. Cancellation / terminal-state races: use conditional `UPDATE ... WHERE status IN (...)` transitions; test on real Postgres.
4. Infra here: Docker engine stopped, Postgres not running; Windows asyncio quirks. (uv now installed.)
5. OR-Tools with asymmetric/unreachable matrices: reject or prune unreachable pairs, never big-M.
6. Scope: large frontend spec (SPEC_FULL sections 13-14) could outpace backend; mitigated by slice-first (D2).
- Postgres queue: stale-claim recovery, polling latency; SKIP LOCKED cannot be tested on SQLite.

## Commands that actually ran, with results
2026-10-28 (M0 environment probe, Windows 11):
- `python --version` -> Python 3.12.0 (`C:\Program Files\Python312`); `py -0p` also lists 3.10 (Microsoft Store). `python3` not found.
- `uv --version` -> not found; not in `~/.local/bin` or `~/.cargo/bin`; `python -m uv` -> No module named uv. `python -m pip --version` -> pip 23.3.1.
- `node --version` -> v22.19.0; `npm --version` -> 10.9.3.
- `git --version` -> 2.49.0.windows.1. Project folder is not a git repository. `gh` not found.
- `docker --version` -> 28.3.2; `docker compose version` -> v2.39.1-desktop.1; `docker info` -> error: `dockerDesktopLinuxEngine` pipe not found (engine not running). `com.docker.service` Stopped; WSL distro `docker-desktop` Stopped.
- `psql` not on PATH; `C:\Program Files\PostgreSQL\18\bin\psql.exe --version` -> 18.1. No Postgres service registered; nothing listening on 5432.
- `redis-server` / `redis-cli` -> not found (not needed, D1).
- Disk C: ~156 GB free.

2026-10-28 (M1):
- `python -m pip install --user uv` -> uv 0.13.6 (on PATH). `git init` -> empty repo created.
- `uv init --lib --name trafiqon --python 3.12 backend`; `uv add numpy` -> numpy 2.5.4; `uv add --dev pytest ruff networkx` -> pytest 9.2.0, ruff 0.17.3, networkx 3.7+.
- `cd backend && uv run pytest` -> `93 passed in 2.08s`.
- `cd backend && uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `21 files already formatted` (after one `ruff format` + `ruff check --fix` pass for formatting and import order).

## Known defects and open items
- Nothing committed yet.
- Scenario `settings` holds traffic/incident metadata as a free-form dict; algorithm config is not on the scenario (it belongs to runs, M2/M4).
- Docs so far: `docs/mathematical_model.md`, `backend/README.md`. No root README yet (M8).
- Docker engine stopped: needed for `docker compose up` (M4/M8). User action: start Docker Desktop.
- No running Postgres: needed for M4 integration tests. Options: Docker Desktop, or a user-owned cluster via local 18.1 `initdb`/`pg_ctl` on a spare port.
- No application code exists yet (greenfield).
