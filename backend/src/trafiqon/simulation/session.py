"""Real-time playback around the deterministic engine.

While RUNNING, simulated time advances lazily at `speed` simulated minutes per wall-clock second:
on each `sync()` (every read or command) the session converts elapsed wall time into WHOLE
ticks and carries the remainder. The engine only ever sees whole ticks, so the resulting state
is a deterministic function of the tick at which each command was applied (recorded in the
event log). The clock is injectable for tests.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

from trafiqon.simulation.engine import (
    SimStatus,
    Simulation,
    SimulationError,
    SimulationStateError,
)
from trafiqon.simulation.replan import replan

MAX_TICKS_PER_SYNC = 20_000  # bounds the work of one request after a long idle period
SPEEDS = (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)


class SimulationSession:
    def __init__(
        self,
        sim: Simulation,
        *,
        speed: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.sim = sim
        self.clock = clock
        self.speed = 1.0
        self.set_speed(speed)
        self._anchor = clock()
        self._carry = 0.0
        self.meta = meta or {}
        self.last_access = clock()

    def set_speed(self, speed: float) -> None:
        if speed not in SPEEDS:
            raise SimulationError(f"speed must be one of {list(SPEEDS)} simulated min per second")
        self.sync()
        self.speed = float(speed)

    def sync(self) -> None:
        now = self.clock()
        self.last_access = now
        if getattr(self, "_anchor", None) is None:
            return
        if self.sim.status is SimStatus.RUNNING:
            sim_minutes = (now - self._anchor) * self.speed + self._carry
            ticks = min(math.floor(sim_minutes / self.sim.tick_minutes + 1e-9), MAX_TICKS_PER_SYNC)
            self.sim.step(ticks)
            self._carry = max(0.0, sim_minutes - ticks * self.sim.tick_minutes)
            if self.sim.status is not SimStatus.RUNNING:
                self._carry = 0.0
        self._anchor = now

    def control(self, action: str, *, ticks: int = 1, speed: float | None = None) -> dict | None:
        """Apply a control action at the current (synced) tick."""
        self.sync()
        sim = self.sim
        if action == "start":
            sim.start()
        elif action == "pause":
            sim.pause()
            self._carry = 0.0
        elif action == "resume":
            sim.resume()
        elif action == "step":
            if sim.status is SimStatus.RUNNING:
                raise SimulationStateError("pause before stepping")
            if not 1 <= ticks <= MAX_TICKS_PER_SYNC:
                raise SimulationError(f"ticks must be between 1 and {MAX_TICKS_PER_SYNC}")
            sim.step(ticks)
        elif action == "reset":
            sim.reset()
            self._carry = 0.0
        elif action == "speed":
            if speed is None:
                raise SimulationError("speed is required")
            self.set_speed(speed)
        elif action == "replan":
            return replan(sim)
        else:
            raise SimulationError(f"unknown action {action!r}")
        self._anchor = self.clock()
        return None


def state_dict(session: SimulationSession, events: int = 50) -> dict[str, Any]:
    """Authoritative, JSON-ready view of a session (after syncing its clock)."""
    session.sync()
    sim = session.sim
    original = sim.scenario.graph.edges
    vehicles = []
    for vid in sorted(sim.vehicles):
        v = sim.vehicles[vid]
        pos = sim.position(v)
        upcoming = ([v.on_edge] if v.on_edge else []) + v.remaining_edges()
        vehicles.append(
            {
                "id": v.id,
                "status": v.status.value,
                "capacity": v.capacity,
                "end_depot_id": v.end_depot_id,
                **pos,
                "completed": v.completed,
                "remaining_stops": v.remaining_stops(),
                "unserved": v.unserved,
                "remaining_edge_ids": upcoming,
                "distance_km": v.distance_km,
                "driving_min": v.driving_min,
                "load_delivered": v.load_delivered,
            }
        )
    overrides = [
        {
            "edge_id": eid,
            "closed": e.closed,
            "current_time": e.current_time,
            "original_current_time": original[eid].current_time,
            "original_closed": original[eid].closed,
        }
        for eid, e in sim.graph.edges.items()
        if e.closed != original[eid].closed
        or abs(e.current_time - original[eid].current_time) > 1e-12
    ]
    served = sum(len(v.completed) for v in sim.vehicles.values())
    return {
        **session.meta,
        "status": sim.status.value,
        "speed": session.speed,
        "speeds": list(SPEEDS),
        "tick": sim.tick,
        "time_min": sim.time,
        "tick_minutes": sim.tick_minutes,
        "plan_version": sim.plan_version,
        "vehicles": vehicles,
        "incidents": [
            {
                "id": i.id,
                "kind": i.kind,
                "edge_ids": i.edge_ids,
                "factor": i.factor,
                "created_at": i.created_at,
                "resolved_at": i.resolved_at,
                "active": i.active,
            }
            for i in sim.incidents.values()
        ],
        "road_overrides": overrides,
        "traffic_factors": dict(sim.traffic_factors),
        "manual_closures": sorted(sim.manual_closures),
        "events": list(sim.events)[-events:],
        "last_replan": sim.last_replan,
        "served_count": served,
        "customer_count": len(sim.scenario.customers),
        "quantity_kinds": {
            "time_min": "simulated",
            "driving_min": "simulated",
            "distance_km": "simulated",
            "latency_ms": "measured",
        },
    }
