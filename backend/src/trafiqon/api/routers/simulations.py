"""Simulation sessions: create, control, authoritative state, incidents, roads, replan.

Sessions live in the API process memory (see STATUS.md D27): they are interactive and
deterministic, are not persisted frame by frame, and are lost if the API restarts. A per-session
lock serializes commands because FastAPI runs sync endpoints concurrently.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy.orm import Session

from trafiqon.api import deps
from trafiqon.api.errors import ApiError
from trafiqon.api.schemas import ErrorResponse, Schema
from trafiqon.persistence import runs as run_repo
from trafiqon.persistence.models import RunRow
from trafiqon.persistence.scenarios import get_version, load_version_scenario
from trafiqon.settings import Settings
from trafiqon.simulation import (
    SPEEDS,
    Simulation,
    SimulationError,
    SimulationSession,
    SimulationStateError,
    construction_routes,
    routes_from_solution,
    solution_from_stored,
    state_dict,
)

router = APIRouter(prefix="/api/v1/simulations", tags=["simulation"])
ERRORS = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class SimulationCreate(Schema):
    scenario_version_id: uuid.UUID
    run_id: uuid.UUID | None = Field(default=None, description="simulate this run's best solution")
    tick_minutes: float = Field(default=0.5, ge=0.05, le=5)
    speed: float = Field(
        default=1.0, description=f"simulated minutes per second, one of {list(SPEEDS)}"
    )


class ControlRequest(Schema):
    action: Literal["start", "pause", "resume", "step", "reset", "speed"]
    ticks: int = Field(default=1, ge=1, le=20_000)
    speed: float | None = None


class IncidentCreate(Schema):
    edge_ids: list[str] = Field(min_length=1, max_length=50)
    kind: Literal["closure", "slowdown"]
    factor: float = Field(default=1.0, ge=1.0, le=100.0, allow_inf_nan=False)


class RoadUpdate(Schema):
    edge_id: str = Field(min_length=1, max_length=200)
    closed: bool | None = None
    traffic_factor: float | None = Field(default=None, gt=0, le=100.0, allow_inf_nan=False)


class _Entry:
    def __init__(self, session: SimulationSession) -> None:
        self.session = session
        self.lock = threading.Lock()


class SimulationManager:
    """In-memory session registry with a size limit and idle expiry."""

    def __init__(self, max_sessions: int, idle_ttl_s: float, clock=time.monotonic) -> None:
        self.max_sessions = max_sessions
        self.idle_ttl_s = idle_ttl_s
        self.clock = clock
        self._sessions: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def _evict(self) -> None:
        now = self.clock()
        for sid in [
            s for s, e in self._sessions.items() if now - e.session.last_access > self.idle_ttl_s
        ]:
            del self._sessions[sid]

    def add(self, session: SimulationSession) -> str:
        with self._lock:
            self._evict()
            if len(self._sessions) >= self.max_sessions:
                raise ApiError(
                    429, "too_many_simulations", "simulation session limit reached; delete one"
                )
            sid = str(uuid.uuid4())
            session.meta["id"] = sid
            self._sessions[sid] = _Entry(session)
            return sid

    def get(self, sid: str) -> _Entry:
        with self._lock:
            self._evict()
            entry = self._sessions.get(sid)
        if entry is None:
            raise ApiError(404, "simulation_not_found", f"simulation {sid} not found (or expired)")
        return entry

    def delete(self, sid: str) -> None:
        with self._lock:
            if self._sessions.pop(sid, None) is None:
                raise ApiError(404, "simulation_not_found", f"simulation {sid} not found")

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._evict()
            return [dict(e.session.meta) for e in self._sessions.values()]


def manager(request: Request) -> SimulationManager:
    return request.app.state.simulations


def _apply(entry: _Entry, fn) -> Any:
    with entry.lock:
        try:
            return fn(entry.session)
        except SimulationStateError as exc:
            raise ApiError(409, "invalid_simulation_state", str(exc)) from None
        except SimulationError as exc:
            raise ApiError(422, "simulation_rejected", str(exc)) from None


@router.post("", status_code=201, responses=ERRORS)
def create_simulation(
    body: SimulationCreate,
    response: Response,
    session: Session = Depends(deps.db),
    sims: SimulationManager = Depends(manager),
) -> dict[str, Any]:
    """Start a session from a run's stored best solution, or from a deterministic
    cheapest-insertion plan when no run is given."""
    version = get_version(session, body.scenario_version_id)
    if version is None:
        raise ApiError(
            404, "version_not_found", f"scenario version {body.scenario_version_id} not found"
        )
    scenario = load_version_scenario(version)
    try:
        if body.run_id is not None:
            run = session.get(RunRow, body.run_id)
            if run is None:
                raise ApiError(404, "run_not_found", f"run {body.run_id} not found")
            if run.scenario_version_id != body.scenario_version_id:
                raise ApiError(
                    422, "version_mismatch", "the run belongs to another scenario version"
                )
            result = run_repo.get_result(session, run.id)
            if result is None or not result.feasible or result.solution is None:
                raise ApiError(
                    409, "no_feasible_solution", "the run has no stored feasible solution"
                )
            routes = routes_from_solution(scenario, solution_from_stored(result.solution))
            source = "run"
        else:
            routes = construction_routes(scenario)
            source = "construction"
        sim = Simulation(scenario, routes, body.tick_minutes)
        sim_session = SimulationSession(
            sim,
            speed=body.speed,
            meta={
                "scenario_version_id": str(body.scenario_version_id),
                "run_id": str(body.run_id) if body.run_id else None,
                "plan_source": source,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
    except SimulationError as exc:
        raise ApiError(422, "simulation_rejected", str(exc)) from None
    sid = sims.add(sim_session)
    response.headers["Location"] = f"/api/v1/simulations/{sid}"
    return _apply(sims.get(sid), state_dict)


@router.get("")
def list_simulations(sims: SimulationManager = Depends(manager)) -> list[dict[str, Any]]:
    return sims.list()


@router.get("/{sid}", responses=ERRORS)
def get_state(sid: str, sims: SimulationManager = Depends(manager)) -> dict[str, Any]:
    """Authoritative state. While running, simulated time advances with wall time."""
    return _apply(sims.get(sid), state_dict)


@router.post("/{sid}/control", responses=ERRORS)
def control(
    sid: str, body: ControlRequest, sims: SimulationManager = Depends(manager)
) -> dict[str, Any]:
    def run(s: SimulationSession):
        s.control(body.action, ticks=body.ticks, speed=body.speed)
        return state_dict(s)

    return _apply(sims.get(sid), run)


@router.post("/{sid}/replan", responses=ERRORS)
def replan_routes(sid: str, sims: SimulationManager = Depends(manager)) -> dict[str, Any]:
    """Replan remaining journeys; returns the replan report and the new state."""

    def run(s: SimulationSession):
        report = s.control("replan")
        return {"replan": report, "state": state_dict(s)}

    return _apply(sims.get(sid), run)


@router.post("/{sid}/incidents", status_code=201, responses=ERRORS)
def create_incident(
    sid: str, body: IncidentCreate, sims: SimulationManager = Depends(manager)
) -> dict[str, Any]:
    def run(s: SimulationSession):
        s.sync()
        s.sim.add_incident(body.edge_ids, body.kind, body.factor)
        return state_dict(s)

    return _apply(sims.get(sid), run)


@router.post("/{sid}/incidents/{incident_id}/resolve", responses=ERRORS)
def resolve_incident(
    sid: str, incident_id: str, sims: SimulationManager = Depends(manager)
) -> dict[str, Any]:
    def run(s: SimulationSession):
        s.sync()
        s.sim.resolve_incident(incident_id)
        return state_dict(s)

    return _apply(sims.get(sid), run)


@router.post("/{sid}/roads", responses=ERRORS)
def update_road(
    sid: str, body: RoadUpdate, sims: SimulationManager = Depends(manager)
) -> dict[str, Any]:
    """Manual closure/reopening and/or traffic factor (relative to the original travel time)."""
    if body.closed is None and body.traffic_factor is None:
        raise ApiError(422, "invalid_request", "provide `closed` and/or `traffic_factor`")

    def run(s: SimulationSession):
        s.sync()
        if body.traffic_factor is not None:
            s.sim.set_traffic(body.edge_id, body.traffic_factor)
        if body.closed is not None:
            s.sim.set_closed(body.edge_id, body.closed)
        return state_dict(s)

    return _apply(sims.get(sid), run)


@router.delete("/{sid}", status_code=204, responses=ERRORS)
def delete_simulation(sid: str, sims: SimulationManager = Depends(manager)) -> Response:
    sims.delete(sid)
    return Response(status_code=204)


def install(app, settings: Settings) -> None:
    app.state.simulations = SimulationManager(
        settings.limits.max_simulations, settings.simulation_idle_ttl_s
    )
    app.include_router(router)
