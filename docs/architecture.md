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
