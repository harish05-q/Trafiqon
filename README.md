# TRAFIQON

A transportation optimization and simulation workbench for the **directed,
capacity-constrained vehicle-routing problem (CVRP) on a road graph**. It supports dynamic
traffic, road incidents and replanning. Three solvers are compared under one shared evaluator:
an OR-Tools reference, Simulated Annealing, and a QPSO-inspired hybrid.

Scope, stated honestly:
- **Not a general solution:** this is not traffic-signal control, traffic assignment or general fleet dispatch.
- **Synthetic data:** the built-in networks are synthetic grids, not real geography.
- **"Quantum-inspired" is classical:** it describes the sampling rule of a classical algorithm. Nothing runs on quantum hardware and no speedup is claimed. The hybrid is documented as *QPSO-inspired*, not canonical QPSO.

## What it does
- **Command Center:**
  - Load or import a scenario, launch a run, and watch live progress (SSE).
  - Cancel a run, inspect its best routes on the map, and compare it with another run.
  - Simulate the routes: step or run the clock, close or slow roads, and replan.
- **Algorithm Lab:**
  - Every algorithm parameter, with its description and limits, published by the backend.
  - Convergence chart, execution statistics, diagnostics, and feasibility checks.
- **Scenario Studio:**
  - Edit nodes, one-way roads, travel times, closures, depots, customers, demand and the fleet.
  - Validate on the server, then save as an immutable version.
- **Experiment Explorer:**
  - Filter run history and compare runs side by side.
  - Benchmark suites (algorithms × seeds) with statistics and seed-level charts.
  - CSV/JSON export with reproducibility metadata.

Every displayed objective comes from one shared evaluator. Unreachable legs are reported as
infeasible, never given a large cost. Runs execute in a separate worker process. Nothing shown
is fabricated: measured, derived and simulated quantities are labelled.

## Architecture
```
 browser ── Next.js (web :3000) ──HTTP/SSE──▶ FastAPI (api :8000) ──SQL──▶ PostgreSQL
                                                     ▲                         ▲
                                                     │ core (pure Python)      │ SKIP LOCKED queue
                                                     │ domain · routing ·      │
                                                     │ optimization ·          │
                                                     │ simulation · experiments│
                                                     ▼                         │
                                              worker process(es) ─────────────┘
```
See [`docs/architecture.md`](docs/architecture.md). The job queue is the `optimization_runs` table, claimed with `FOR UPDATE SKIP LOCKED`; Celery + Redis is deferred (STATUS.md, D1).

## Quick start (Docker)
Requires Docker with Compose v2.
```bash
docker compose up --build
```
Then open http://localhost:3000. On startup:
1. `migrate` runs Alembic on an empty database and exits.
2. `api`, `worker` and `web` start.

To run a first optimization: in the Command Center, import "Urban Grid", then press **Launch run**.

Ports are configurable. The browser calls the API directly, so set its public URL too:
```bash
API_PORT=8200 WEB_PORT=3200 PUBLIC_API_URL=http://localhost:8200 PUBLIC_WEB_URL=http://localhost:3200 docker compose up --build
```

This local stack has no password and publishes the database port. To put TRAFIQON on the internet (free, one VM, HTTPS, password, same-origin API), use the production override described in [`docs/deployment.md`](docs/deployment.md).

## Local development
Prerequisites:
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 22 and npm
- Docker, for PostgreSQL

```bash
docker compose up -d db                       # PostgreSQL 18 on :5432
cd backend && uv sync
export TRAFIQON_DATABASE_URL=postgresql+psycopg://trafiqon:trafiqon@localhost:5432/trafiqon
uv run alembic upgrade head                   # migrations from a clean database
uv run uvicorn trafiqon.api.app:app --port 8000      # API   (terminal 1)
uv run python -m trafiqon.worker.main                # worker (terminal 2)
cd ../frontend && npm ci && npm run dev              # web on :3000 (terminal 3)
```
On Windows PowerShell, set the variable with `$env:TRAFIQON_DATABASE_URL = "..."`. Copy
`.env.example` for all settings.

## Tests and checks
```bash
cd backend  && uv run pytest                                   # unit + integration (real PostgreSQL)
cd backend  && uv run ruff check . && uv run ruff format --check .
cd frontend && npm test                                        # Vitest
cd frontend && npm run lint && npm run build                   # ESLint + Prettier, production build
cd frontend && npx playwright install chromium && npx playwright test   # E2E workflows 1-6 + a11y
```
- **Integration tests** use `trafiqon_test`. It is created and migrated automatically, and the tests are skipped and reported as NOT RUN if PostgreSQL is unreachable.
- **Playwright** starts its own stack: API on :8100, a real worker, and a production build on :3100, against a fresh `trafiqon_e2e` database.
- **CI:** `.github/workflows/ci.yml` runs all of the above.

## Configuration
All settings come from environment variables; see [`.env.example`](.env.example).
- **Database:** `TRAFIQON_DATABASE_URL`. Without it the API still serves the built-in scenarios and shortest paths, and answers 503 for the rest.
- **CORS:** `TRAFIQON_CORS_ORIGINS`.
- **Worker timing:** heartbeat, stale-run timeout, maximum attempts.
- **Request limits:** `TRAFIQON_LIMIT_*`.
- **Frontend:** `NEXT_PUBLIC_API_BASE_URL`, inlined at build time.

## Troubleshooting
- **"API: unreachable" in the top bar:** the web app cannot reach `NEXT_PUBLIC_API_BASE_URL`. Check that the API is running and that its URL and port match what the web build was given.
- **CORS errors in the browser console:** add the web origin to `TRAFIQON_CORS_ORIGINS`.
- **"DB: unavailable":** start PostgreSQL (`docker compose up -d db`) and check `TRAFIQON_DATABASE_URL`. `GET /api/v1/ready` returns 503 until the database is reachable.
- **Runs stay QUEUED:** no worker is running. Start one with `python -m trafiqon.worker.main`.
- **Simulation panel says the previous session is gone:** simulation sessions live in the API's memory and are lost when it restarts (D27). Start a new one.
- **Docker errors mentioning `dockerDesktopLinuxEngine`:** Docker Desktop is not running.
- **Node tools fail to connect to `localhost` but `127.0.0.1` works:** Node may resolve `localhost` to IPv6 `::1` while uvicorn listens on IPv4. The E2E config uses `127.0.0.1`.

## Documentation
| Document | Contents |
|---|---|
| [`docs/mathematical_model.md`](docs/mathematical_model.md) | Graph, CVRP, objective, constraints, evaluator |
| [`docs/algorithms.md`](docs/algorithms.md) | Shortest paths, OR-Tools, SA, the QPSO-inspired formulation, complexity, limitations |
| [`docs/benchmark_methodology.md`](docs/benchmark_methodology.md) | Budgets, seeds, statistics, gap reference, exports |
| [`docs/simulation.md`](docs/simulation.md) | Clock, vehicle state, incidents, replanning |
| [`docs/api_contracts.md`](docs/api_contracts.md) | Endpoints, errors, SSE events, run lifecycle |
| [`docs/architecture.md`](docs/architecture.md) | Components, data flow, infrastructure decisions |
| [`docs/deployment.md`](docs/deployment.md) | Free public deployment: Oracle Cloud Always Free VM, Caddy HTTPS + password, backups, troubleshooting |
| [`docs/interview_guide.md`](docs/interview_guide.md) | Decisions, trade-offs, failure modes, likely questions |
| [`STATUS.md`](STATUS.md) | Milestones, decisions (D1–D36), commands actually run, known defects |

## Limitations
These are known and documented, not hidden:
- The benchmark fixtures are small synthetic grids, plus one 30-customer experimental grid.
- Gaps are measured against the best observed result, not a proven optimum.
- There is no exact or lower-bound method.
- Simulation sessions are in-memory, for a single API process.
- There is no authentication; `owner_id` columns mark where it will plug in.
- See STATUS.md, "Known defects and open items".
