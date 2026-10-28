"""Deterministic discrete-time simulation of vehicles executing routes on the road graph.

Semantics (docs/simulation.md):
- Time advances in fixed ticks of `tick_minutes`. Within a tick each vehicle spends exactly the
  tick's time budget along its plan: partial edge traversal, arrivals and stop completions
  happen at exact intra-tick times. Nothing teleports and nothing overshoots.
- A vehicle on an edge is described by `progress` in [0, 1]. Its remaining time is
  (1 - progress) * current_time(edge) under CURRENT conditions, so a traffic change on an edge
  a vehicle is already on keeps its progress and re-times only the rest of the edge.
- Closures stop vehicles ENTERING an edge. A vehicle already on an edge that gets closed finishes
  it. A vehicle whose next planned edge is closed waits at the node ("blocked") until the edge
  reopens or the route is replanned.
- Road conditions are layered: original edge -> manual traffic factor -> manual closure ->
  active incidents (closure, or slowdown factor). Resolving an incident recomputes from the layers.
- Same initial plan + same sequence of (tick, action) gives the same state.
"""

from __future__ import annotations

import copy
import math
from collections import deque
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from trafiqon.domain.models import Edge, Graph, Scenario

EPS = 1e-9
MAX_EVENTS = 500


class SimStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


class VehicleStatus(StrEnum):
    EN_ROUTE = "en_route"
    BLOCKED = "blocked"  # next planned edge is closed; waiting at a node
    FINISHED = "finished"  # reached its end depot with no stops left
    IDLE = "idle"  # no route assigned


@dataclass
class Leg:
    """Path from the previous stop to `stop_id` (a customer) or to the end depot (None)."""

    stop_id: str | None
    target_node: str
    edge_ids: list[str]


@dataclass
class PlannedRoute:
    vehicle_id: str
    start_depot_id: str
    end_depot_id: str
    legs: list[Leg]


@dataclass
class VehicleState:
    id: str
    capacity: int
    end_depot_id: str
    end_node: str
    legs: list[Leg]
    node: str | None  # current node when not on an edge
    on_edge: str | None = None
    progress: float = 0.0
    # Index into legs[0].edge_ids of the NEXT edge to enter (incremented on entry, so the edge
    # being traversed is never part of the remaining plan; a replan starts at its target node).
    edge_index: int = 0
    status: VehicleStatus = VehicleStatus.EN_ROUTE
    completed: list[dict[str, Any]] = field(default_factory=list)
    unserved: list[str] = field(default_factory=list)
    distance_km: float = 0.0
    driving_min: float = 0.0
    load_delivered: int = 0

    def remaining_stops(self) -> list[str]:
        return [leg.stop_id for leg in self.legs if leg.stop_id is not None]

    def remaining_edges(self) -> list[str]:
        if not self.legs:
            return []
        first = self.legs[0].edge_ids[max(self.edge_index, 0) :]
        return first + [e for leg in self.legs[1:] for e in leg.edge_ids]


@dataclass
class Incident:
    id: str
    kind: str  # "closure" | "slowdown"
    edge_ids: list[str]
    factor: float
    created_at: float
    created_tick: int
    resolved_at: float | None = None
    resolved_tick: int | None = None

    @property
    def active(self) -> bool:
        return self.resolved_at is None


class SimulationError(ValueError):
    pass


class SimulationStateError(SimulationError):
    """The command is not allowed in the current status (e.g. pause when not running)."""


class Simulation:
    def __init__(self, scenario: Scenario, routes: list[PlannedRoute], tick_minutes: float = 0.5):
        if not (tick_minutes > 0 and math.isfinite(tick_minutes)):
            raise SimulationError("tick_minutes must be a positive number")
        self.scenario = scenario
        self.tick_minutes = float(tick_minutes)
        self._initial_routes = copy.deepcopy(routes)
        self._original_edges: dict[str, Edge] = dict(scenario.graph.edges)
        self._validate_routes(routes)
        self.reset()

    # -- setup --------------------------------------------------------------------------------

    def _validate_routes(self, routes: list[PlannedRoute]) -> None:
        depots = {d.id: d.node_id for d in self.scenario.depots}
        customers = {c.id: c.node_id for c in self.scenario.customers}
        vehicles = {v.id for v in self.scenario.vehicles}
        for r in routes:
            if r.vehicle_id not in vehicles:
                raise SimulationError(f"unknown vehicle {r.vehicle_id!r}")
            node = depots.get(r.start_depot_id)
            if node is None or r.end_depot_id not in depots:
                raise SimulationError(f"vehicle {r.vehicle_id!r}: unknown depot")
            for leg in r.legs:
                for eid in leg.edge_ids:
                    e = self._original_edges.get(eid)
                    if e is None or e.source != node:
                        raise SimulationError(
                            f"vehicle {r.vehicle_id!r}: discontinuous path at {eid!r}"
                        )
                    node = e.target
                expected = customers.get(leg.stop_id) if leg.stop_id else depots[r.end_depot_id]
                if node != leg.target_node or node != expected:
                    raise SimulationError(f"vehicle {r.vehicle_id!r}: leg does not reach its stop")

    def reset(self) -> None:
        """Back to time 0: initial plan, original road conditions, no incidents."""
        self.time = 0.0
        self.tick = 0
        self.status = SimStatus.READY
        self.traffic_factors: dict[str, float] = {}
        self.manual_closures: set[str] = set()
        self.incidents: dict[str, Incident] = {}
        self.events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self.plan_version = 0
        self.last_replan: dict[str, Any] | None = None
        self.graph: Graph = self.scenario.graph
        depots = {d.id: d.node_id for d in self.scenario.depots}
        routes = {r.vehicle_id: r for r in copy.deepcopy(self._initial_routes)}
        self.vehicles: dict[str, VehicleState] = {}
        for v in self.scenario.vehicles:
            r = routes.get(v.id)
            end = r.end_depot_id if r else (v.end_depot_ids or (v.start_depot_id,))[0]
            self.vehicles[v.id] = VehicleState(
                id=v.id,
                capacity=v.capacity,
                end_depot_id=end,
                end_node=depots[end],
                legs=r.legs if r else [],
                node=depots[r.start_depot_id if r else v.start_depot_id],
                status=VehicleStatus.EN_ROUTE if r and r.legs else VehicleStatus.IDLE,
            )
        self._log("reset", {})

    # -- controls -----------------------------------------------------------------------------

    def start(self) -> None:
        if self.status is not SimStatus.READY:
            raise SimulationStateError(f"cannot start from {self.status}")
        self.status = SimStatus.RUNNING
        self._log("started", {})

    def pause(self) -> None:
        if self.status is not SimStatus.RUNNING:
            raise SimulationStateError(f"cannot pause from {self.status}")
        self.status = SimStatus.PAUSED
        self._log("paused", {})

    def resume(self) -> None:
        if self.status is not SimStatus.PAUSED:
            raise SimulationStateError(f"cannot resume from {self.status}")
        self.status = SimStatus.RUNNING
        self._log("resumed", {})

    def step(self, ticks: int = 1) -> None:
        """Advance exactly `ticks` ticks (allowed in any status except finished)."""
        if ticks < 0:
            raise SimulationError("ticks must be >= 0")
        for _ in range(ticks):
            if self.status is SimStatus.FINISHED:
                return
            start = self.time
            for vid in sorted(self.vehicles):  # fixed order: deterministic event log
                self._advance(self.vehicles[vid], start, self.tick_minutes)
            self.tick += 1
            self.time = self.tick * self.tick_minutes  # no float drift accumulation
            if all(
                v.status in (VehicleStatus.FINISHED, VehicleStatus.IDLE)
                for v in self.vehicles.values()
            ):
                self.status = SimStatus.FINISHED
                self._log("finished", {})

    # -- road conditions ----------------------------------------------------------------------

    def _edge(self, edge_id: str) -> Edge:
        if edge_id not in self._original_edges:
            raise SimulationError(f"unknown edge {edge_id!r}")
        return self.graph.edges[edge_id]

    def _rebuild_graph(self) -> None:
        factors = dict(self.traffic_factors)
        closed = set(self.manual_closures)
        for inc in self.incidents.values():
            if not inc.active:
                continue
            for eid in inc.edge_ids:
                if inc.kind == "closure":
                    closed.add(eid)
                else:
                    factors[eid] = factors.get(eid, 1.0) * inc.factor
        edges = []
        for eid, orig in self._original_edges.items():
            f = factors.get(eid, 1.0)
            edges.append(
                replace(
                    orig,
                    current_time=orig.current_time * f,
                    closed=orig.closed or eid in closed,
                    congestion=(orig.congestion or 1.0) * f,
                )
            )
        self.graph = Graph(self.scenario.graph.nodes.values(), edges)
        # Blocked vehicles may move again if their next edge reopened (checked on next tick).

    def set_traffic(self, edge_id: str, factor: float) -> None:
        """Set a manual travel-time multiplier relative to the ORIGINAL current_time."""
        self._edge(edge_id)
        if not (factor > 0 and math.isfinite(factor)):
            raise SimulationError("factor must be a positive number")
        if factor == 1.0:
            self.traffic_factors.pop(edge_id, None)
        else:
            self.traffic_factors[edge_id] = float(factor)
        self._rebuild_graph()
        self._log("traffic_changed", {"edge_id": edge_id, "factor": factor})

    def set_closed(self, edge_id: str, closed: bool) -> None:
        self._edge(edge_id)
        (self.manual_closures.add if closed else self.manual_closures.discard)(edge_id)
        self._rebuild_graph()
        self._log("road_closed" if closed else "road_reopened", {"edge_id": edge_id})

    def add_incident(self, edge_ids: list[str], kind: str, factor: float = 1.0) -> Incident:
        if kind not in ("closure", "slowdown"):
            raise SimulationError("kind must be 'closure' or 'slowdown'")
        if not edge_ids:
            raise SimulationError("an incident needs at least one edge")
        for eid in edge_ids:
            self._edge(eid)
        if kind == "slowdown" and not (factor >= 1.0 and math.isfinite(factor)):
            raise SimulationError("slowdown factor must be >= 1")
        inc = Incident(
            f"inc-{len(self.incidents) + 1}",
            kind,
            list(dict.fromkeys(edge_ids)),
            float(factor if kind == "slowdown" else 1.0),
            self.time,
            self.tick,
        )
        self.incidents[inc.id] = inc
        self._rebuild_graph()
        self._log(
            "incident_created",
            {"incident_id": inc.id, "kind": kind, "edge_ids": inc.edge_ids, "factor": inc.factor},
        )
        return inc

    def resolve_incident(self, incident_id: str) -> Incident:
        inc = self.incidents.get(incident_id)
        if inc is None:
            raise SimulationError(f"unknown incident {incident_id!r}")
        if inc.active:
            inc.resolved_at, inc.resolved_tick = self.time, self.tick
            self._rebuild_graph()
            self._log("incident_resolved", {"incident_id": inc.id})
        return inc

    # -- movement -----------------------------------------------------------------------------

    def _advance(self, v: VehicleState, tick_start: float, budget: float) -> None:
        if v.status in (VehicleStatus.FINISHED, VehicleStatus.IDLE):
            return
        used = 0.0
        while True:
            if v.on_edge is None:
                # Zero-time transitions happen even when the tick's budget is spent, so a stop
                # reached exactly at a tick boundary is completed in that tick.
                if not v.legs:
                    if v.node == v.end_node:
                        v.status = VehicleStatus.FINISHED
                        self._log("vehicle_finished", {"vehicle_id": v.id}, tick_start + used)
                    elif v.status is not VehicleStatus.BLOCKED:
                        v.status = VehicleStatus.BLOCKED  # stranded away from its end depot
                        self._log(
                            "vehicle_stranded",
                            {"vehicle_id": v.id, "node": v.node},
                            tick_start + used,
                        )
                    return
                leg = v.legs[0]
                if v.edge_index >= len(leg.edge_ids):
                    self._complete_leg(v, tick_start + used)
                    continue
                if budget - used <= EPS:
                    return
                edge = self.graph.edges[leg.edge_ids[v.edge_index]]
                if edge.closed:
                    if v.status is not VehicleStatus.BLOCKED:
                        v.status = VehicleStatus.BLOCKED
                        self._log(
                            "vehicle_blocked",
                            {"vehicle_id": v.id, "node": v.node, "edge_id": edge.id},
                            tick_start + used,
                        )
                    return
                if v.status is VehicleStatus.BLOCKED:
                    v.status = VehicleStatus.EN_ROUTE
                    self._log("vehicle_unblocked", {"vehicle_id": v.id}, tick_start + used)
                v.on_edge, v.progress, v.node = edge.id, 0.0, None
                v.edge_index += 1
            if budget - used <= EPS:
                return
            edge = self.graph.edges[v.on_edge]
            if edge.current_time <= EPS:
                v.progress = 1.0
            else:
                need = (1.0 - v.progress) * edge.current_time
                spend = min(need, budget - used)
                v.progress = min(1.0, v.progress + spend / edge.current_time)
                v.driving_min += spend
                used += spend
            if v.progress >= 1.0 - EPS:
                v.distance_km += edge.distance
                v.node, v.on_edge, v.progress = edge.target, None, 0.0

    def _complete_leg(self, v: VehicleState, at: float) -> None:
        leg = v.legs.pop(0)
        v.edge_index = 0
        if leg.stop_id is not None:
            demand = next(c.demand for c in self.scenario.customers if c.id == leg.stop_id)
            v.load_delivered += demand
            v.completed.append({"customer_id": leg.stop_id, "time": round(at, 6), "node": v.node})
            self._log("stop_completed", {"vehicle_id": v.id, "customer_id": leg.stop_id}, at)

    # -- views --------------------------------------------------------------------------------

    def position(self, v: VehicleState) -> dict[str, Any]:
        nodes = self.graph.nodes
        if v.on_edge is None:
            n = nodes[v.node]  # type: ignore[index]
            return {"node": v.node, "edge_id": None, "progress": None, "x": n.x, "y": n.y}
        e = self.graph.edges[v.on_edge]
        a, b = nodes[e.source], nodes[e.target]
        x = y = None
        if a.has_coordinates and b.has_coordinates:
            x = a.x + (b.x - a.x) * v.progress  # type: ignore[operator]
            y = a.y + (b.y - a.y) * v.progress  # type: ignore[operator]
        return {
            "node": None,
            "edge_id": e.id,
            "progress": v.progress,
            "x": x,
            "y": y,
            "remaining_on_edge_min": (1 - v.progress) * e.current_time,
        }

    def _log(self, kind: str, details: dict[str, Any], at: float | None = None) -> None:
        self.events.append(
            {
                "time": round(self.time if at is None else at, 6),
                "tick": self.tick,
                "type": kind,
                **details,
            }
        )
