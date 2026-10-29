# TRAFIQON Status



Update this file at the end of every work session. It is the source of truth after a context reset.



## Current milestone

M8 done and committed (2026-10-29). All planned milestones (M0-M8) are done; see the Definition of Done walk below for what is and is not verified. Full stack: `docker compose up --build` (Docker Desktop must be running); tests need `docker compose up -d db`.



## Milestones

| # | Name | State | Acceptance criteria met |

|---|---|---|---|

| 0 | Inspect and plan | done | Inventory, structure, conflicts, infra findings, plan, risks, slice reported (2026-10-28) |

| 1 | Domain + routing (Dijkstra, A*) | done | All M1 criteria below; 93 tests, ruff clean (2026-10-28) |

| 1.5 | Thin vertical slice (D2) | done | API + TestClient tests, Vitest, drawn path == API path checked in browser (2026-10-28) |

| 2 | OR-Tools + SA + common interface | done | Contract, OR-Tools, SA, evaluator parity, determinism, cancellation, infeasible handling, baseline experiments + CSV/JSON; 165 tests (2026-10-28) |

| 3 | QPSO-inspired optimizer | done | Math written first (docs/algorithms.md); encode/decode/update/repair/LS tests, determinism, cancellation, evaluator parity, measured ablation, limitations; 205 tests (2026-10-28) |

| 4 | Persistence, API, worker | done | Alembic from clean DB, immutable versions (DB trigger), runs/results/events/suites, Postgres SKIP LOCKED queue + worker process, SSE, cancel, idempotency, recovery; 60 integration tests on real Postgres 18.6 (2026-10-28) |

| 5 | Frontend foundation + design system | done | Tokens (exact spec values, test-checked), dark/light theme, shell, panels, status components, React Flow road renderer, TanStack Query + SSE + Zustand on the real API; lint/build/32 Vitest pass; live run/cancel verified in browser (2026-10-28) |

| 6 | Four workspaces end to end | done | Command Center (compare routes), Algorithm Lab (param specs, convergence), Scenario Studio (edit/validate/save version), Experiment Explorer (run comparison, suites, export); 58 Vitest; Playwright E2E 1-4 pass on the real stack (2026-10-28) |

| 7 | Simulation + replanning | done | Deterministic tick engine (exact intra-tick timing, no teleporting), defined traffic/closure-on-edge semantics, layered incidents, state-preserving replan with latency/disruption, real-time sessions, simulation API, Command Center UI, Playwright E2E 5 (2026-10-29) |

| 8 | Hardening, benchmarks, docs | done | Seed-level benchmark chart from stored results, export verified against stored results (E2E 6), axe WCAG 2 A/AA audit of all workspaces in both themes + keyboard test, full Compose stack (db/migrate/api/worker/web) verified from a clean volume, CI workflow, root README, interview guide, docs reviewed; 320 backend, 71 Vitest, 9 Playwright pass (2026-10-29) |



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

- D13 (2026-10-28): QPSO hybrid (`qpso_hybrid` v1) = canonical QPSO position update (mean-best attractor, linear beta 1.0 -> 0.5) on 2n continuous random keys (assignment floor-map + order keys), deterministic decode, two-phase repair, first-improvement relocate/swap/2-opt local search, Lamarckian write-back via exact inverse encoding. Documented as QPSO-inspired, not canonical QPSO; no quantum claims. `update_rule: "uniform_resample"` exists only as a labelled ablation baseline.

- D14 (2026-10-28): `RoutingProblem` keeps plain-list copies of the matrix/locations/demands for speed (route_cost is the hot loop). Added `fixtures.builtin.experimental_grid` as a seeded larger-experimental synthetic instance (not a UI built-in).

- D15 (2026-10-28): M4 design. The run row is the queue entry (enqueue = INSERT QUEUED in the API transaction). Claim via `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`. All transitions are conditional UPDATEs, ownership-checked by `worker_id`. complete() = status + result insert in one tx, and a CANCELLING run (or a cancelled algorithm) ends CANCELLED. Retry only on worker loss (stale heartbeat), bounded by max_attempts=2; algorithm exceptions are FAILED and not retried. At-least-once delivery; exactly-once NOT claimed. One run per worker process.

- D16 (2026-10-28): Benchmark suites are sets of ordinary runs (suite_id FK) created in one transaction; comparison/export are computed from stored COMPLETED results only (cancelled/failed/unfinished counted, never imputed). Experiment API = /suites.

- D17 (2026-10-28): Scenario versions are immutable via a Postgres BEFORE UPDATE trigger; deleting a scenario is refused (409) if any run or suite references its versions. `owner_id` columns are present but unused (auth-ready boundary). Algorithms gained `uses_seed`; the API generates and records a seed before execution for seeded algorithms.

- D18 (2026-10-28): SSE polls `run_events` (0.5 s) through the threadpool; reads run status BEFORE events so a terminal status always comes with its final events (a race found and fixed by test). Progress events are throttled and capped per run; the latest summary is on the run row; old progress events of finished runs are pruned.

- D19 (2026-10-28): Design tokens live only in `frontend/src/app/globals.css` (`--tq-*`, dark default, `[data-theme=light]`), mapped onto shadcn/ui variables; `src/styles/tokens.test.ts` asserts the exact SPEC_FULL 13.2/13.3 values and WCAG contrast. Derived (non-spec) tokens, each with a stated reason: road graphite, on-signal text, light-theme incident/ochre/traffic/road/muted variants, a 4-colour series palette disjoint from traffic colours, and `--tq-signal-fill` #b8432c for filled controls in light theme because the spec light accent #d94f35 cannot carry AA small text in white (4.10:1) or black. Strokes/routes keep #d94f35.

- D20 (2026-10-28): shadcn/ui (radix base, nova preset) for primitives; generated files in `src/components/ui` are excluded from Prettier. A token-styled native `<select>` is used for accessibility/testability. Fonts: Inter + JetBrains Mono (shadcn's Geist removed). `vite-tsconfig-paths` dropped for Vite's native `resolve.tsconfigPaths`.

- D21 (2026-10-28): The M1.5 RouteSlice page was replaced by the Command Center (route group `(workspaces)`, `/` redirects). Algorithm Lab, Scenario Studio and Experiment Explorer pages are explicit "not implemented yet (M6)" notices with no mock data. The run launcher exposes only budget parameters (+ seed for seeded algorithms); everything else is the server default. Workspace state (theme, version, active run, panels) persists in localStorage via Zustand so jobs survive refresh/navigation; server state is TanStack Query; SSE via EventSource with id-deduping reducer.

- D22 (2026-10-28): Map display rule: an open road is "congested" when current_time / base_time >= 1.25 (display only). Two-way roads are drawn offset 3 px per direction; status is never colour-only (dash pattern for closed, text labels, `<title>` tooltips).

- D23 (2026-10-28): Algorithms publish `ParamSpec`s (core metadata, no framework deps); `GET /algorithms` returns them with maxima capped by server limits. A unit test asserts specs == config keys and agree with resolve_config at their bounds. The Lab form is generated from them and submits only changed values.
- D24 (2026-10-28): New endpoints: `POST /scenarios/validate` (structure, capacity, reachability, strongly connected components via iterative Tarjan in `routing/connectivity.py`; `feasible_so_far` is explicitly not a proof); run filters `scenario_id`, `created_after`, `created_before`.
- D25 (2026-10-28): Per-workspace themes: operational workspaces start dark, Experiment Explorer starts light (one theme per workspace, never mixed). One SSE EventSource per active run, mounted in the shell; logs shared through a store. Command Center "compare routes" overlays another completed run's routes (dotted, series colour). Simulation, incidents and replanning are NOT in M6 (M7): the top bar says "Simulation: not available".
- D26 (2026-10-28): E2E stack: Playwright starts the API (:8100, waits on /health because webServers start before globalSetup) and a production build (:3100); globalSetup drops/recreates `trafiqon_e2e`, migrates from clean, and spawns a real worker process. Explicit 127.0.0.1 URLs (Node resolves localhost to ::1).
- D27 (2026-10-29): Simulation sessions live in the API process memory (bounded by `max_simulations`, idle TTL), with a per-session lock; not persisted frame by frame (SPEC_FULL 12) and lost on API restart (the UI says so). Assumes a single API process; persisting a command log for replay is possible because the engine is deterministic per (tick, command).
- D28 (2026-10-29): Engine semantics: position = progress in [0,1] on an edge; a tick's time budget is spent exactly (zero-time transitions such as stop completion happen even with no budget left). Traffic change on the current edge keeps progress and re-times the remainder; closures block entry only (a vehicle on a newly closed edge finishes it); a closed next edge -> `blocked` until reopen or replan. Conditions are layered (original, manual factor, manual closure, incidents) and recomputed on resolve.
- D29 (2026-10-29): Replanning keeps the clock, positions, the edge in progress and completed stops; each vehicle keeps its own remaining customers (goods on board) plus previously unserved ones; order = exact permutations up to 7 stops (tested never worse than the old order), else cheapest insertion + 2-opt. Unreachable stops -> `unserved`; unreachable end depot -> stranded vehicle reported (serves stops at its own node); the simulation is never reported finished while a vehicle is stranded. Latency is measured; disruption (stops reordered, segments changed) is derived.
- D30 (2026-10-29): Real-time playback converts wall time into whole ticks with carry at `speed` simulated min/s (fixed set 0.25-30), at most 20,000 ticks per request. The frontend polls every 400 ms while running and only interpolates marker movement with a CSS transition (off under reduced motion).
- D31 (2026-10-29): Text colour rules from the a11y audit: the spec's muted token (#77786f) is 3.96:1 on the dark surface, so it is kept for borders/decoration only and small text uses `text-muted-foreground`. Status colours used as text get `--tq-*-text` tokens (signal, incident), and the light theme's derived traffic-normal/congested are darkened; a token test asserts >= 4.5:1 on every surface in both themes. The spec palette values themselves are unchanged.
- D32 (2026-10-29): The suite comparison endpoint also returns seed-level rows of COMPLETED runs (`runs`); the Explorer draws them as a per-seed scatter with the mean marked, so spread is visible, not just aggregates.
- D33 (2026-10-29): Compose runs the full stack: `db`, one-shot `migrate` (`alembic upgrade head`), `api`, `worker`, `web` (Next standalone build, enabled only when `NEXT_OUTPUT=standalone` so local `next start`/E2E are unchanged). Host ports and the browser-visible API URL are variables (`DB_PORT`, `API_PORT`, `WEB_PORT`, `PUBLIC_API_URL`); `NEXT_PUBLIC_API_BASE_URL` is baked at image build time. Alembic `env.py` only configures logging if none is configured, so the migrate container logs its upgrades.
- D34 (2026-10-29): CI (`.github/workflows/ci.yml`): backend (Postgres 18 service, ruff, pytest), frontend (lint, Vitest, build), E2E (Playwright, artifacts on failure), and image builds. Validated as YAML locally only; it has NOT run on GitHub (no remote configured).
- D35 (2026-10-29): Scrollable workspace panels are focusable (`tabIndex=0` + aria-label) so keyboard users can scroll them (WCAG 2.1.1, axe scrollable-region-focusable). The keyboard E2E accepts either the token outline or the shadcn focus ring as the visible focus indicator. Map nodes/vehicle markers with an aria-label get `role="img"`.
- D36 (2026-10-29): The axe audit excludes only React Flow's attribution link (third-party). Audits run on the production build with real data, including a mid-simulation state.
- D37 (2026-10-29): Free public deployment = one Oracle Cloud Always Free Ampere A1 VM running the whole Compose stack, because the worker must run continuously and simulation sessions need one long-lived API process (free PaaS tiers sleep or lack workers). `docker-compose.prod.yml` + `deploy/Caddyfile`: only Caddy is published (automatic HTTPS, basic auth for the whole site, since the app has no accounts), DB password from `deploy/.env`, the web app built with an empty API base URL so it calls `/api/...` on its own origin (no CORS, auth covers the API and SSE), log rotation. Guide: `docs/deployment.md`.
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



2026-10-28 (M3):

- `cd backend && uv run pytest` -> `205 passed in 10.29s`. `uv run ruff check .` -> `All checks passed!`; format check clean.

- `uv run python -m trafiqon.experiments.ablation_qpso --seeds 5 --out results/ablation` (measured; gap vs best observed heuristic):

  - congested_city: qpso/no-ls mean 74.660 (gap 1.17 %, 0.11 s); resample/no-ls 77.800 (5.42 %); qpso/ls 73.800 (0.00 %, 0.29 s); resample/ls 73.800 (0.00 %, 0.55 s).

  - experimental_grid_s0_n30: qpso/no-ls 261.664 (23.61 %, std 8.36); resample/no-ls 277.139 (30.92 %, std 9.49); qpso/ls 211.758 (0.04 %, 5.29 s); resample/ls 212.934 (0.59 %, 5.81 s).

  - QPSO <= resample on mean in all 4 settings (tie on congested_city/ls). n=5, no significance test.

- `uv run python -m trafiqon.experiments.baseline --seeds 5 --out results/baseline`: all three algorithms 5/5 feasible on all three built-ins; QPSO mean equals the reference on each (73.800 / 60.792 / 55.153) at 1.25 / 0.48 / 1.34 s; OR-Tools 1.00 s; SA 0.14-0.16 s, SA mean 74.920 on congested_city.

- One-off timing on experimental_grid_s0_n30, seed 0: QPSO 15x30 with LS 211.679 (5.02 s); SA default 211.826 (0.2 s); OR-Tools 2 s 218.515.



2026-10-28 (M4):

- `uv add sqlalchemy alembic "psycopg[binary]"` -> sqlalchemy 2.1.6, alembic 1.20.1, psycopg 3.3.6.

- `docker compose up -d db` -> postgres:18 container healthy (PostgreSQL 18.6).

- `alembic upgrade head`, `alembic check` -> "No new upgrade operations detected"; `alembic downgrade base` + `upgrade head` OK.

- `cd backend && uv run pytest` -> `265 passed in 110.00s` (205 unit + 60 integration on real Postgres; the session drops/recreates the schema and migrates from clean; the test DB is auto-created).

- With an unreachable DB URL the integration tests report `SKIPPED ... integration tests NOT RUN` (checked).

- `uv run ruff check .` -> `All checks passed!`; `ruff format --check .` -> `63 files already formatted`.

- First integration run: 4 failures were wrong test expectations (server limits correctly rejected configs); 1 real bug: SSE could end before sending final events (read order); fixed, then the test passed 5/5 reruns.

- Manual e2e with separate processes (uvicorn :8001 + `python -m trafiqon.worker.main --migrate`): created scenario from congested_city, submitted qpso_hybrid (iterations 40, seed 5); SSE showed queued, started, 2x progress, completed, end; run COMPLETED attempt 1, objective 73.8, feasible, 1.07 s.



2026-10-28 (M5):

- `npx shadcn@latest init -t next -b radix -p nova` (first try without `-p` stopped at an interactive preset prompt) and `shadcn add input label select tabs tooltip badge separator scroll-area`; `npm install zustand` (5.0.16). First `@types/node` peer conflict not re-hit.

- `cd frontend && npm test` -> `Test Files 5 passed, Tests 32 passed` (tokens 7, toFlow 8, events 4, AppShell 5, CommandCenter 8). The first token test run failed on a real issue (spec light accent vs small-text contrast), fixed via D19.

- `npm run lint` -> ESLint clean, `All matched files use Prettier code style!`. `npm run build` -> `Compiled successfully`, 8/8 static pages.

- Live check (built-in browser; API with DB on :8000, worker process, `next dev` on :3000), verified via DOM because the pane could not render screenshots: imported Congested City; header showed `Congested City v1 · synthetic` and `API: online · DB: ok`; launched qpso_hybrid (60 iterations, seed 7): QUEUED -> RUNNING -> COMPLETED, event log streamed over SSE, objective 73.800 min, routes 22.05 + 14.60 + 31.05 + 6.10 = 73.80; after a page reload, the scenario, run and result were restored. Launched SA (2M iterations) and cancelled from the UI: RUNNING -> CANCELLING -> CANCELLED, best-so-far 78.500 kept, "stopped: cancelled".

- Found and fixed in the live check: the monitor showed the last throttled progress report (iteration 49 of 60) as if final; it is now labelled as such, and the final iteration/evaluation counts appear under Best solution.



2026-10-28 (M6):
- `npm install echarts` (6.1.0), `npm install -D @playwright/test` (1.64.1), `npx playwright install chromium`.
- `cd backend && uv run pytest` -> `281 passed in 46.05s` (adds param-spec/SCC unit tests and M6 API integration tests). `ruff check` -> `All checks passed!`; `ruff format --check` -> `66 files already formatted`.
- `cd frontend && npm test` -> `Test Files 9 passed, Tests 58 passed`. `npm run lint` -> ESLint clean (after fixing 3 react-hooks errors: memo deps, setState-in-effect x2), Prettier clean. `tsc --noEmit` clean.
- `cd frontend && npx playwright test` -> `5 passed (46.7s)`: E2E 1 load built-in/run/inspect (asserts drawn on-route edges == stored evaluator legs in a real rendered browser), 2 edit in Studio/save v2/run on v2 (closed road unused), 3 progress then cancel -> CANCELLED (second cancel unchanged), 4 compare two completed runs; plus a screenshot capture. Earlier failed attempts were setup issues (IPv6 localhost, webServer-before-globalSetup ordering, multi-line `python -c` under the Windows shell) and ambiguous selectors in the screenshot spec.
- Visual review from Playwright screenshots (first time the map was seen rendered): routes, congestion, depots/customers, the light Explorer theme and the convergence chart all render. Fixed from the review: dimmed routes kept orange arrowheads; selected road was indistinct; legend permanently covered the map (now collapsible). One blank chart screenshot was a capture-timing issue (verified rendered: 34 SVG paths).
- Repaired one STATUS.md line that an earlier edit had written in cp1252; all repo text files now decode as UTF-8.

2026-10-29 (M7):
- `cd backend && uv run pytest` -> `320 passed in 43.33s` (adds 33 simulation unit tests and 6 simulation API integration tests). First run of the new unit tests: 6 failures. Real engine bug: arrivals exactly at a tick boundary completed one tick late (fixed: zero-time transitions). Real replan bug: an unreachable end depot raised instead of being reported (fixed with an explicit stranded policy). Plus one wrong test expectation (equal-cost orders on the line graph), replaced by a property test.
- `uv run ruff check .` -> `All checks passed!`; `ruff format --check .` -> `74 files already formatted`.
- `cd frontend && npm test` -> `Tests 66 passed`; `npm run lint` clean; `tsc --noEmit` clean.
- `cd frontend && npx playwright test` -> 6 passed (E2E 1-5 + screenshots); E2E 5 passed on its first run. Final rerun after the UI fixes below: `6 passed (50.9s)`, and the new simulation screenshot shows the fixes.
- Integration check: simulated driving time of a completed run's plan == its evaluator objective when nothing changes.
- Visual review (Playwright screenshot mid-simulation with an incident and a replan): vehicles render at backend positions with remaining paths. Fixed from the review: vehicle labels showed the internal node id (`vehicle:v2`); the inspector showed the ORIGINAL road status ("normal") for a road closed in the simulation (now uses the simulation's effective roads; regression test added); a selected closed road lost its dash pattern.

2026-10-29 (M8):
- `cd backend && uv run pytest` -> `320 passed in 47.11s`; `ruff check .` -> `All checks passed!`; `ruff format --check .` -> `74 files already formatted`.
- `cd frontend && npm test` -> `Test Files 11 passed, Tests 71 passed`; `npm run lint` -> ESLint clean and Prettier clean (after `prettier --write next.config.ts`); `npm run build` -> `Compiled successfully`.
- `cd frontend && npx playwright test` -> `9 passed (1.4m)`: E2E 1-6, a11y audit, keyboard test, screenshots. Getting there took four a11y rounds, all real findings: aria-label on role-less divs (19 nodes), muted text contrast (18 nodes, D31), light traffic-normal text on secondary (3.88:1), unfocusable scroll regions (D35), and the inactive tab trigger (`text-foreground/60`) in the light theme.
- E2E 6 (export): suite run through the worker; JSON and CSV downloaded through the UI match the stored suite/runs (ids, version fingerprint, seeds, budget policy, evaluator version, software versions, per-run objective/seed, reference label). Passed.
- `docker compose up --build` on a clean volume (separate project, ports 5442/8300/3300, then `down -v`): migrate exited 0 (`Running upgrade -> 0001`), api healthy, web healthy; a run launched from the browser was executed by the worker container: COMPLETED, objective 73.800. First build attempt failed in `npm ci` (transient, during parallel builds); the rebuild passed.
- CI YAML parsed with `yaml.safe_load`; not run on GitHub.

2026-10-29 (deployment guide, after M8):
- Production override run locally (`-p tqprod`, `SITE_ADDRESS=:80`, host port 8088): all services up; only Caddy publishes ports. curl: page and API 401 without/with wrong password, 200 with it; `/api/v1/ready` ok; a qpso_hybrid run submitted through Caddy COMPLETED (objective 73.8) with SSE events queued/started/progress/completed/end through the proxy.
- Browser (Playwright with HTTP credentials): all requests to localhost:8088 only; import, SA run to COMPLETED with live events, still there after reload. Web bundle has no `localhost:8000`.
- `down` + `up -d` kept the runs; `pg_dump --format=custom` restored into a fresh DB with equal counts (2 runs, 8 events); in-place `pg_restore --clean --if-exists` with api/worker stopped exited 0 and the API came back with the runs.
- `docker buildx build --platform linux/arm64 backend` (QEMU) succeeded; on it: `aarch64 9.15.6755 2.5.4 3.3.6` (OR-Tools, NumPy, psycopg) and an OR-Tools routing solve returned the correct tour cost 15.
- `docker compose up --wait` exits non-zero because the worker has no healthcheck (by design); the guide does not use `--wait`.
- Not verified: a real Oracle VM, Let's Encrypt on a public domain, DuckDNS, Cloudflare quick tunnel, the frontend image on arm64 (node:22-alpine is multi-arch; not built).

## Definition of Done walk (SPEC_FULL section 20, 2026-10-29)
Functionality:
- Starts via documented workflow: yes (README Docker quick start, verified from a clean volume).
- Migrations from clean DB: yes (Compose migrate, E2E globalSetup, integration tests).
- Built-in scenarios load/inspect; graph editing + validation; Dijkstra/A*; OR-Tools and SA correctly evaluated; QPSO implements its documented update; one evaluator: yes, unit/integration tested (M1-M3) and E2E 1-2.
- Runs through the worker; progress is real; cancellation/failure states; persistence across refresh: yes (M4 integration on real Postgres, E2E 3, browser checks).
- Simulation follows authoritative state; incidents affect costs/availability; replanning preserves positions and completed stops: yes (M7 tests, E2E 5).
- Benchmarks/exports from stored results: yes (E2E 6).
Visual quality:
- Branding, central tokens, dark palette, warm light theme, map-first layout, no neon remnants: yes, by token tests and screenshot review at 1440x900 only.
- Charts with labels/units/legends from real data: yes (convergence, seed scatter).
- Empty/loading/failure/cancellation states: present and exercised in E2E for the main flows; not every edge state was reviewed visually.
- Keyboard and reduced motion: axe A/AA clean and a Tab-reachability test pass; reduced motion disables marker transitions. Canvas road selection is mouse/pointer only (roads are also selectable in lists). No screen-reader user testing.
Engineering quality:
- Tests, lint, format, builds pass: yes (above). CI not run remotely.
- No known critical defects in required workflows: none known.
- No fabricated metrics: all figures shown come from stored runs; the app shows "not proven optimal" wording for heuristics.
- Docs reflect implementation: reviewed in M8 (README, architecture, api_contracts, algorithms, benchmark_methodology, interview_guide).
- Reproducible setup: Docker path verified on this Windows machine only.
Not done / partial: "improve performance" was limited to bounded limits and the existing throttling; no profiling pass or larger-instance benchmark campaign. Mobile/small screens not tested on a device.

## Known defects and open items
- Deployment: guide verified locally only (see 2026-10-29 deployment entry); no app-level accounts, the site-wide Caddy password is the only access control.
- M8: CI never run on GitHub. No performance profiling; QPSO local search still dominates runtime (M3). Small-screen layouts untested on devices. Screenshot review at 1440x900 only. The Compose stack on API 8200 / web 3200 used during M8 may still be running (`docker compose down` to stop; keep `db` for tests).
- M7: simulation sessions are in-memory (single API process, lost on restart; D27). No service time at stops (arrival = service). Customers are never reassigned between vehicles during replanning (deliberate, D29). Replanning uses its own exact/heuristic ordering, not the QPSO/SA/OR-Tools optimizers.
- M6: no Playwright E2E 5 (simulation, M7) or 6 (export metadata vs stored result, M8). Studio has no undo; multiple end depots per vehicle are not editable in the Studio (the API supports them). The run history table has no objective column (results are fetched per selected run). Screenshots were reviewed at 1440x900 only.

- M5: the map's visual rendering (React Flow edges/route overlay) was NOT verified by screenshot: the browser pane could not composite frames while the Claude window was not in view, and React Flow does not measure nodes then (36 nodes in the DOM, edges not drawn). Component tests cover what is handed to the renderer; a visual check is still owed. No ECharts convergence chart yet (M6/M8). Light theme exists but no workspace defaults to it yet. Small-screen layout stacks panels under the map; not tested on a device.

- M4: no simulation API yet (M7). No per-client rate limiting; job submission is bounded by the queued-run limit only. SSE uses DB polling (fine for one node). The frontend still uses only the built-in endpoints (M5/M6 connect it). Compose has only the `db` service (api/worker/web in M8). No CI yet (M8).

- M3: local search dominates QPSO runtime (about 5 s on 30 customers); not faster than SA there. Only one larger-experimental instance has been measured.

- M2: the small fixtures are easy (both methods tie on 2 of 3); larger experimental scenarios are needed before comparisons mean much (M8). No exact/lower-bound method yet, so every gap is vs a heuristic reference. Not yet in the API (runs/worker arrive in M4).

- Slice UI is minimal: fixed-width side panels (cramped below ~1000px), no light theme, no keyboard path selection on the canvas (selects work via keyboard). M5 replaces it with the real shell.

- No Playwright yet (M6); the drawn-path check above was manual via the built-in browser plus a Vitest wiring test.

- Scenario `settings` holds traffic/incident metadata as a free-form dict; algorithm config is not on the scenario (it belongs to runs, M2/M4).

- Docs so far: `docs/mathematical_model.md`, `backend/README.md`. No root README yet (M8).

- Docker engine stopped: needed for `docker compose up` (M4/M8). User action: start Docker Desktop.

- No running Postgres: needed for M4 integration tests. Options: Docker Desktop, or a user-owned cluster via local 18.1 `initdb`/`pg_ctl` on a spare port.


