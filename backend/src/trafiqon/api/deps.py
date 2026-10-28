"""Request-scoped dependencies: settings, DB session, job queue."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from trafiqon.api.errors import ApiError
from trafiqon.settings import Settings
from trafiqon.worker.queue import JobQueue


@dataclass
class AppState:
    settings: Settings
    engine: Engine | None
    factory: sessionmaker[Session] | None
    queue: JobQueue | None


def state(request: Request) -> AppState:
    return request.app.state.trafiqon


def settings(request: Request) -> Settings:
    return state(request).settings


def db(request: Request) -> Iterator[Session]:
    """A session per request. Handlers commit explicitly; anything uncommitted is rolled back."""
    st = state(request)
    if st.factory is None:
        raise ApiError(503, "database_not_configured", "TRAFIQON_DATABASE_URL is not set")
    session = st.factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def queue(request: Request) -> JobQueue:
    q = state(request).queue
    if q is None:
        raise ApiError(503, "database_not_configured", "TRAFIQON_DATABASE_URL is not set")
    return q
