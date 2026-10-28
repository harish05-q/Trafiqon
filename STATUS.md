# TRAFIQON Status

Update this file at the end of every work session. It is the source of truth after a context reset.

## Current milestone
M2 done (2026-10-28), not yet committed (M1.5 is commit 1c265e3). Next: M3 (QPSO-inspired optimizer; write docs/algorithms.md section first).

## Milestones
| # | Name | State | Acceptance criteria met |
|---|---|---|---|
| 0 | Inspect and plan | done | Inventory, structure, conflicts, infra findings, plan, risks, slice reported (2026-10-28) |
| 1 | Domain + routing (Dijkstra, A*) | done | All M1 criteria below; 93 tests, ruff clean (2026-10-28) |
| 1.5 | Thin vertical slice (D2) | done | API + TestClient tests, Vitest, drawn path == API path checked in browser (2026-10-28) |
| 2 | OR-Tools + SA + common interface | done | Contract, OR-Tools, SA, evaluator parity, determinism, cancellation, infeasible handling, baseline experiments + CSV/JSON; 165 tests (2026-10-28) |
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
- D7 (2026-10-28): Frontend is Next.js 16.4.3 / React 19.3 (current create-next-app); its bundled docs (`frontend/node_modules/next/dist/docs`, per `frontend/AGENTS.md`) are the reference. `@types/node` pinned to ^22 to match Node 22 and vitest 5 peer range. `npm run lint` = ESLint + `prettier --check` (D3). API tests use `httpx2` (Starlette deprecates httpx for TestClient).
- D8 (2026-10-28): The slice API serves built-in fixtures only (no DB). `/routing/shortest-path` re-validates and re-costs the found path with the shared evaluator (`evaluate_leg`) before returning it. Health reports `database: not_configured` honestly until M4.
- D9 (2026-10-28): Shared search representation = one customer list per vehicle (`optimization/problem.py`); internal costs use the cost matrix with +inf for unreachable legs (search-only, never reported). Every reported objective is re-scored by the shared evaluator in `contract.finalize`; rejected candidates are dropped and their violations kept in diagnostics.
- D10 (2026-10-28): SA handles capacity with an explicit penalty term (lambda x overload, default 2 x longest leg) so it can cross infeasible states; only overload-free states become the incumbent and the reported objective is pure travel time. Unreachable legs are hard-rejected.
- D11 (2026-10-28): OR-Tools: unreachable arcs removed from NextVar domains (no big-M); multiple allowed end depots via per-vehicle dummy end nodes; integer cost scale 1000/min; `proven_optimal` only on ROUTING_OPTIMAL (w.r.t. scaled costs). No seed, not deterministic under a time limit (recorded). Optional exact small-instance method NOT implemented (SPEC_FULL 7.3 marks it optional).
- D12 (2026-10-28): Budgets differ by design: OR-Tools by wall time, SA by iterations (deterministic per seed); both wall times are recorded. Gap reference = proven optimum if any, else best observed heuristic, labelled. See docs/benchmark_methodology.md.
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

2026-10-28 (M1.5):
- `uv add fastapi "uvicorn[standard]"` -> fastapi 0.162.0, pydantic 2.14.1, starlette 1.10.0, uvicorn 0.54.0; dev `httpx2` 2.16.0.
- `npx create-next-app@latest frontend --ts --tailwind --eslint --app --src-dir` -> next 16.4.3, react 19.3.0. Added @xyflow/react 12.12, @tanstack/react-query 5.105; dev vitest 5.0.5, @testing-library/react 16.3, jsdom 29, prettier 3.9. First vitest install failed on a peer conflict (@types/node ^20 vs vitest); fixed by @types/node ^22.
- `cd backend && uv run pytest` -> `108 passed` (93 unit + 15 API). `uv run ruff check .` -> `All checks passed!`; `ruff format --check .` -> `27 files already formatted`.
- `cd frontend && npm test` -> `Test Files 2 passed, Tests 8 passed`. `npm run lint` -> no ESLint output, `All matched files use Prettier code style!`. `npm run build` -> `Compiled successfully`, 4/4 static pages.
- Browser check (built-in browser, API on :8000 + `next dev` on :3000): Incident Response n2_1 -> n2_2: API edges `n2_1->n3_1, n3_1->n3_2, n3_2->n2_2` (6.5 min) == React Flow `.on-path` edges == listed edges; the 3 incident edges render as `.closed`. Congested City n0_0 -> n5_5: drawn on-path set == API set, 10.65 min shown. At 1280x760 all nodes fit in view after a scenario switch. Note: with the pane hidden, React Flow does not measure nodes and draws no edges (environmental, not an app bug).

2026-10-28 (M2):
- `uv add ortools` -> ortools 9.15.6755, protobuf 6.33.6.
- `cd backend && uv run pytest` -> `165 passed in 8.62s` (warning filter added for SWIG DeprecationWarnings from OR-Tools import).
- `uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `37 files already formatted`.
- `uv run python -m trafiqon.experiments.baseline --seeds 5 --out results/baseline` (measured on this machine; synthetic fixtures; OR-Tools 1.0 s limit, SA 20k iterations; gap vs best observed heuristic, not an optimum):
  - congested_city: ref 73.800 min. OR-Tools 5/5 feasible, mean 73.800, std 0.000, 1.00 s. SA 5/5, mean 74.920, median 73.950, std 1.553, best 73.800, gap 1.52 %, 0.26 s.
  - incident_response: ref 60.792. OR-Tools mean 60.792 (1.00 s); SA mean 60.792, std 0 (0.21 s).
  - urban_grid: ref 55.153. OR-Tools mean 55.153 (1.00 s); SA mean 55.153, std 0 (0.27 s).

## Known defects and open items
- M2: the small fixtures are easy (both methods tie on 2 of 3); larger experimental scenarios are needed before comparisons mean much (M8). No exact/lower-bound method yet, so every gap is vs a heuristic reference. Not yet in the API (runs/worker arrive in M4).
- Slice UI is minimal: fixed-width side panels (cramped below ~1000px), no light theme, no keyboard path selection on the canvas (selects work via keyboard). M5 replaces it with the real shell.
- No Playwright yet (M6); the drawn-path check above was manual via the built-in browser plus a Vitest wiring test.
- Nothing committed yet.
- Scenario `settings` holds traffic/incident metadata as a free-form dict; algorithm config is not on the scenario (it belongs to runs, M2/M4).
- Docs so far: `docs/mathematical_model.md`, `backend/README.md`. No root README yet (M8).
- Docker engine stopped: needed for `docker compose up` (M4/M8). User action: start Docker Desktop.
- No running Postgres: needed for M4 integration tests. Options: Docker Desktop, or a user-owned cluster via local 18.1 `initdb`/`pg_ctl` on a spare port.
- No application code exists yet (greenfield).
