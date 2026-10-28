"""Optimization runs: submit, status, SSE progress, cancel, result, history.

The handler only persists a QUEUED run (the queue entry) and returns; execution happens in
the worker process. Retry semantics: see worker/queue.py and docs/api_contracts.md.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trafiqon.api import deps
from trafiqon.api.errors import ApiError
from trafiqon.api.schemas import (
    CancelResponse,
    ErrorResponse,
    Page,
    RunCreate,
    RunOut,
    RunResultOut,
)
from trafiqon.optimization import Algorithm, ConfigError, get_algorithm
from trafiqon.persistence import runs as repo
from trafiqon.persistence.db import session_scope
from trafiqon.persistence.models import TERMINAL, RunRow, RunStatus
from trafiqon.persistence.scenarios import get_version
from trafiqon.settings import Limits, Settings
from trafiqon.worker.queue import JobQueue

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])
ERRORS = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


def server_caps(algorithm_id: str, limits: Limits) -> dict[str, float]:
    """Server-side maxima per config key (on top of each algorithm's own ranges)."""
    caps: dict[str, float] = {"time_limit_s": limits.max_time_limit_s}
    if algorithm_id == "simulated_annealing":
        caps["max_iterations"] = limits.max_sa_iterations
    if algorithm_id == "qpso_hybrid":
        caps["swarm_size"] = limits.max_qpso_swarm
        caps["iterations"] = limits.max_qpso_iterations
    return caps


def check_limits(algorithm_id: str, cfg: dict[str, Any], limits: Limits) -> None:
    """Bound execution cost per request (SPEC_FULL section 15)."""
    caps = server_caps(algorithm_id, limits)
    over = {
        k: {"value": cfg[k], "limit": cap}
        for k, cap in caps.items()
        if cap is not None and cfg.get(k) is not None and cfg[k] > cap
    }
    if over:
        raise ApiError(422, "config_exceeds_limits", "configuration exceeds server limits", over)


def prepare(
    algorithm_id: str, config: dict[str, Any], seed: int | None, limits: Limits
) -> tuple[Algorithm, dict[str, Any], int | None]:
    try:
        algorithm = get_algorithm(algorithm_id)
        resolved = algorithm.resolve_config(config)
    except ConfigError as exc:
        raise ApiError(422, "invalid_config", str(exc)) from None
    check_limits(algorithm_id, resolved, limits)
    if not algorithm.uses_seed:
        seed = None
    elif seed is None:
        seed = secrets.randbits(63)  # recorded before execution, so the run is reproducible
    return algorithm, resolved, seed


def run_out(row: RunRow) -> RunOut:
    return RunOut.model_validate(row, from_attributes=True)


def _load(session: Session, run_id: uuid.UUID) -> RunRow:
    row = session.get(RunRow, run_id)
    if row is None:
        raise ApiError(404, "run_not_found", f"run {run_id} not found")
    return row


@router.post("", status_code=202, response_model=RunOut, responses=ERRORS)
def submit_run(
    body: RunCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, max_length=200),
    session: Session = Depends(deps.db),
    queue: JobQueue = Depends(deps.queue),
    settings: Settings = Depends(deps.settings),
) -> RunOut:
    """Persist the run as QUEUED, then acknowledge (202). With an idempotency key, repeating
    the same request returns the original run (200); a different request with the same key
    is rejected (409)."""
    key = body.idempotency_key or idempotency_key
    fingerprint = repo.request_fingerprint(body.model_dump(exclude={"idempotency_key"}))
    if key:
        existing = repo.find_by_idempotency_key(session, key)
        if existing is not None:
            return _replay(existing, fingerprint, response)
    if get_version(session, body.scenario_version_id) is None:
        raise ApiError(
            404, "version_not_found", f"scenario version {body.scenario_version_id} not found"
        )
    algorithm, config, seed = prepare(body.algorithm_id, body.config, body.seed, settings.limits)
    if repo.count_queued(session) >= settings.limits.max_queued_runs:
        raise ApiError(429, "queue_full", "too many queued runs; retry later")
    row = repo.new_run(
        scenario_version_id=body.scenario_version_id,
        algorithm_id=algorithm.id,
        algorithm_version=algorithm.version,
        config=config,
        seed=seed,
        max_attempts=settings.max_attempts,
        idempotency_key=key,
        fingerprint=fingerprint,
    )
    try:
        queue.enqueue(session, row)
        session.commit()
    except IntegrityError:  # concurrent request with the same idempotency key won the insert
        session.rollback()
        existing = repo.find_by_idempotency_key(session, key) if key else None
        if existing is None:
            raise
        return _replay(existing, fingerprint, response)
    response.headers["Location"] = f"/api/v1/runs/{row.id}"
    return run_out(row)


def _replay(existing: RunRow, fingerprint: str, response: Response) -> RunOut:
    if existing.request_fingerprint != fingerprint:
        raise ApiError(
            409, "idempotency_conflict", "idempotency key was already used with a different request"
        )
    response.status_code = 200
    response.headers["Location"] = f"/api/v1/runs/{existing.id}"
    return run_out(existing)


@router.get("", response_model=Page[RunOut])
def list_runs(
    status: RunStatus | None = None,
    algorithm_id: str | None = None,
    scenario_version_id: uuid.UUID | None = None,
    suite_id: uuid.UUID | None = None,
    scenario_id: uuid.UUID | None = Query(None, description="any version of this scenario"),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(deps.db),
) -> Page[RunOut]:
    flt = repo.RunFilter(
        status.value if status else None,
        algorithm_id,
        scenario_version_id,
        suite_id,
        scenario_id,
        created_after,
        created_before,
    )
    rows, total = repo.list_runs(session, flt, limit, offset)
    return Page[RunOut](items=[run_out(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunOut, responses=ERRORS)
def get_run(run_id: uuid.UUID, session: Session = Depends(deps.db)) -> RunOut:
    return run_out(_load(session, run_id))


@router.post("/{run_id}/cancel", response_model=CancelResponse, responses=ERRORS)
def cancel_run(
    run_id: uuid.UUID,
    response: Response,
    session: Session = Depends(deps.db),
    queue: JobQueue = Depends(deps.queue),
) -> CancelResponse:
    """Idempotent. QUEUED runs are cancelled immediately; RUNNING runs move to CANCELLING and
    the worker stops cooperatively (202). Terminal runs are left unchanged (200)."""
    before = _load(session, run_id).status
    status = queue.request_cancel(session, run_id)
    session.commit()
    if status is None:
        raise ApiError(404, "run_not_found", f"run {run_id} not found")
    response.status_code = 200 if before in TERMINAL or before == RunStatus.CANCELLING else 202
    return CancelResponse(id=run_id, status=status)


@router.get("/{run_id}/result", response_model=RunResultOut, responses=ERRORS)
def get_result(run_id: uuid.UUID, session: Session = Depends(deps.db)) -> RunResultOut:
    """Available once the run is COMPLETED, or CANCELLED after it started (best-so-far)."""
    run = _load(session, run_id)
    result = repo.get_result(session, run_id)
    if result is None:
        raise ApiError(
            404, "result_not_available", f"run {run_id} has no result (status {run.status})"
        )
    return RunResultOut.model_validate(result, from_attributes=True)


@router.get("/{run_id}/events", responses=ERRORS, response_class=StreamingResponse)
async def stream_events(
    run_id: uuid.UUID,
    request: Request,
    after: int = Query(0, ge=0, description="resume after this event id"),
    last_event_id: str | None = Header(default=None),
) -> StreamingResponse:
    """Server-Sent Events from `run_events`. Each event carries `id:` so clients can resume
    with Last-Event-ID. The stream ends with `event: end` once the run is terminal and all
    events were sent, or after the configured maximum duration (client should reconnect)."""
    st = deps.state(request)
    if st.factory is None:
        raise ApiError(503, "database_not_configured", "TRAFIQON_DATABASE_URL is not set")
    factory = st.factory
    with session_scope(factory) as s:
        _load(s, run_id)
    cursor = after
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    def fetch(c: int) -> tuple[list[dict[str, Any]], str]:
        # Status FIRST: a terminal status commits together with its lifecycle event, so the
        # events query below is guaranteed to include it. (Reading events first could miss
        # events committed in between and end the stream early.)
        with session_scope(factory) as s:
            status = s.scalar(select(RunRow.status).where(RunRow.id == run_id))
            events = repo.events_after(s, run_id, c)
            return [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "type": e.type,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ], status

    async def gen():
        nonlocal cursor
        started = last_ping = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            events, status = await run_in_threadpool(fetch, cursor)
            for e in events:
                cursor = e["id"]
                yield f"id: {e['id']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"
            if not events and status in TERMINAL:
                yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
                return
            now = time.monotonic()
            if now - started > st.settings.sse_max_duration_s:
                yield "event: timeout\ndata: {}\n\n"
                return
            if now - last_ping > 15:
                last_ping = now
                yield ": keep-alive\n\n"
            if not events:
                await asyncio.sleep(st.settings.sse_poll_interval_s)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
