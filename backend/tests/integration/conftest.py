"""Integration tests against a REAL PostgreSQL database.

URL: TRAFIQON_TEST_DATABASE_URL (default: the docker compose `db` service, database
`trafiqon_test`). The schema is dropped and rebuilt with Alembic migrations once per session
(exercising migrations from a clean database); tables are truncated before each test.
If PostgreSQL is unreachable every test here is SKIPPED and reported as not run.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text

from trafiqon.api.app import create_app
from trafiqon.optimization import ALGORITHMS
from trafiqon.persistence.db import make_engine, make_session_factory, migrate
from trafiqon.settings import Limits, Settings
from trafiqon.worker.main import Worker
from trafiqon.worker.queue import PostgresJobQueue

DEFAULT_URL = "postgresql+psycopg://trafiqon:trafiqon@localhost:5432/trafiqon_test"
TABLES = (
    "run_events, run_results, optimization_runs, benchmark_suites, scenario_versions, scenarios"
)


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


def _ensure_database(url: str) -> None:
    """Create the test database on the server if it does not exist (best effort)."""
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    except Exception:  # pragma: no cover - unreachable server is handled by the caller
        pass
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.environ.get("TRAFIQON_TEST_DATABASE_URL", DEFAULT_URL)
    _ensure_database(url)
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on environment
        pytest.skip(f"PostgreSQL not reachable ({type(exc).__name__}); integration tests NOT RUN")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    migrate(url)
    return url


@pytest.fixture(scope="session")
def engine(pg_url):
    eng = make_engine(pg_url)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    return make_session_factory(engine)


@pytest.fixture
def settings(pg_url) -> Settings:
    return Settings(
        database_url=pg_url,
        heartbeat_interval_s=0.05,
        stale_after_s=0.5,
        progress_event_min_interval_s=0.0,
        worker_poll_interval_s=0.05,
        sse_poll_interval_s=0.05,
        limits=Limits(max_queued_runs=50, max_suite_runs=30, max_simulations=5),
    )


@pytest.fixture
def queue(factory, settings) -> PostgresJobQueue:
    return PostgresJobQueue(factory, stale_after_s=settings.stale_after_s)


@pytest.fixture
def client(factory, settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
    app.state.trafiqon.engine.dispose()


@pytest.fixture
def make_worker(factory, queue, settings) -> Callable[..., Worker]:
    def make(worker_id: str = "w1", algorithms=None, **overrides) -> Worker:
        return Worker(
            factory,
            queue,
            replace(settings, **overrides),
            worker_id=worker_id,
            algorithms={**ALGORITHMS, **(algorithms or {})},
        )

    return make


@pytest.fixture
def version_id(client) -> str:
    r = client.post("/api/v1/scenarios", json={"name": "Urban", "builtin_id": "urban_grid"})
    assert r.status_code == 201, r.text
    return r.json()["current_version_id"]


def wait_for(predicate: Callable[[], bool], timeout: float = 10.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("condition not met within timeout")


def in_thread(fn: Callable[[], object]) -> tuple[threading.Thread, list]:
    out: list = []
    t = threading.Thread(target=lambda: out.append(fn()), daemon=True)
    t.start()
    return t, out
