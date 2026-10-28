# Architecture (as implemented through M4)

A modular monolith with a separately running worker process.

```
frontend (Next.js)  --HTTP/SSE-->  api (FastAPI)  --SQL-->  PostgreSQL  <--SQL--  worker process(es)
                                       |                                             |
                                       +----------- core (pure Python) --------------+
                     domain · routing · optimization · experiments · fixtures
```

## Packages (`backend/src/trafiqon`)
- **Core**, with no web, database or queue imports (enforced by `tests/unit/test_import_boundaries.py`):
  - `domain`: graph, scenario, solution, validation, serialization.
  - `routing`: Dijkstra, A*, cost matrix, and the single evaluator.
  - `optimization`: the common contract, OR-Tools, SA and the QPSO hybrid.
  - `experiments`: the runner, statistics and exports.
  - `fixtures`.
- `persistence`: SQLAlchemy 2 models, repositories, and Alembic migrations (`persistence/migrations`).
- `worker`: the `JobQueue` interface, `PostgresJobQueue`, and the `Worker` process (`python -m trafiqon.worker.main`).
- `api`: the FastAPI app factory, routers, Pydantic schemas and the error shape.
- `settings.py`: environment-based settings and limits. Only `api` and `worker` read them.

## Job execution (decision D1: Postgres queue, not Celery + Redis)
- **Enqueue:** `optimization_runs` rows are the queue. Enqueueing means inserting a `QUEUED` row in the API request's transaction, so a run is either durably queued or not created at all. No outbox is needed.
- **Claim:** `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`. Concurrent workers never claim the same run (tested with 8 threads × 40 runs on real Postgres).
- **Heartbeat:** a worker thread refreshes `heartbeat_at` every `heartbeat_interval_s`. It reads back `CANCELLING`, or detects lost ownership, and sets the algorithm's cooperative cancel flag.
- **Complete:** status update and result insert happen in one transaction.
- **Recovery and lifecycle:** stale recovery, retry semantics and the lifecycle are described in `api_contracts.md`.
- **Concurrency:** one run per worker process. Run more workers to scale. The API applies a queued-run limit.

## Trade-offs
- **Polling:** idle workers poll every `worker_poll_interval_s` (0.5 s by default) instead of being pushed work. That adds latency, but nothing else is needed. `LISTEN/NOTIFY` could be added later behind the same interface.
- **SSE:** streams poll `run_events` every 0.5 s through the API's thread pool. This suits a single-node deployment.
- **Celery + Redis:** could be added as another `JobQueue` implementation without changing optimizers or the API (see STATUS.md D1).
- **Synchronous drivers:** sync SQLAlchemy/psycopg everywhere, which avoids Windows asyncio event-loop issues. Async endpoints (SSE) call the database through the thread pool.

## Frontend (`frontend/`, Next.js App Router)
- **Workspaces:** route group `(workspaces)`: Command Center, Algorithm Lab, Scenario Studio, Experiment Explorer. They share the shell (`components/shell`).
- **Server state:** TanStack Query only (`lib/api/hooks.ts`, typed client `lib/api/client.ts`). Nothing in the UI invents server data.
- **Client state:** Zustand (`stores/workspace.ts`) holds the per-workspace theme, loaded scenario version, active and comparison run, and panel layout. It is persisted to localStorage, so jobs survive navigation and refresh.
- **Live progress:** one `EventSource` per active run, mounted once in the shell (`ActiveRunStream`). It feeds a shared, id-deduplicating event log (`lib/api/events.ts`) and invalidates queries on lifecycle events. Polling is only a fallback.
- **Parameter forms:** generated from `GET /algorithms` parameter specs, which carry descriptions, ranges and server caps. Only values changed from the defaults are submitted.
- **Scenario Studio:** edits go through a pure draft reducer (`features/scenario-studio/draft.ts`) that rejects invalid edits with a message. The server validates (`POST /scenarios/validate`) and saves immutable versions.
- **Charts:** ECharts via a small wrapper. The option builder is a pure, tested function; series colours come from the series tokens. The chart shows stored history after a run, or live progress reports during one, labelled as such.
- **Themes:** design tokens live only in `app/globals.css`. Operational workspaces start dark; the Experiment Explorer starts on the warm light theme.
- **Tests:** Vitest (`src/**/*.test.ts(x)`) uses real-shaped API fixtures (`src/test/fake-api.ts`). Playwright (`e2e/`) runs against the real stack: a migrated e2e database, the API on :8100, a separate worker process, and a production build on :3100.

## Simulation
- **Engine:** `simulation/` is a pure-Python deterministic tick engine with replanning; see `simulation.md`.
- **Real-time sessions:** the API process holds them in memory, behind a per-session lock (D27).
- **Polling:** the browser polls the authoritative state while a session runs.

## Delivery
- **`docker-compose.yml`:**
  - `db` (PostgreSQL 18);
  - `migrate` (a one-shot `alembic upgrade head`);
  - `api` (uvicorn, health check on `/api/v1/ready`);
  - `worker` (the same backend image);
  - `web` (Next.js standalone build; the browser-facing API URL is a build argument).
- **CI** (`.github/workflows/ci.yml`):
  - backend lint and tests against a PostgreSQL service;
  - frontend lint, tests and build;
  - Playwright end-to-end workflows 1–6 and accessibility;
  - Compose image build.
