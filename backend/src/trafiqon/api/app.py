"""FastAPI application factory.

    TRAFIQON_DATABASE_URL=postgresql+psycopg://... uv run uvicorn trafiqon.api.app:app

Without a database URL the DB-free routes (built-in scenarios, shortest path, health) still
work and DB-backed routes answer 503 `database_not_configured`.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trafiqon import __version__
from trafiqon.api.deps import AppState
from trafiqon.api.errors import install_error_handlers
from trafiqon.api.routers import health, runs, scenarios, suites
from trafiqon.api.routes import router as builtin_router
from trafiqon.persistence.db import make_engine, make_session_factory
from trafiqon.settings import Settings
from trafiqon.worker.queue import PostgresJobQueue

log = logging.getLogger("trafiqon.api")


def create_app(
    settings: Settings | None = None, *, cors_origins: list[str] | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    if cors_origins is not None:
        settings = replace(settings, cors_origins=tuple(cors_origins))
    engine = factory = queue = None
    if settings.database_url:
        engine = make_engine(settings.database_url)
        factory = make_session_factory(engine)
        queue = PostgresJobQueue(factory, stale_after_s=settings.stale_after_s)

    app = FastAPI(title="TRAFIQON API", version=__version__)
    app.state.trafiqon = AppState(settings, engine, factory, queue)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID"],
        expose_headers=["Location"],
    )
    install_error_handlers(app)
    for router in (
        health.router,
        builtin_router,
        scenarios.router,
        scenarios.versions_router,
        runs.router,
        suites.router,
    ):
        app.include_router(router)
    log.info(
        "TRAFIQON API %s, database %s, CORS %s",
        __version__,
        "configured" if engine else "not configured",
        list(settings.cors_origins),
    )
    return app


app = create_app()
