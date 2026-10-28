"""Remaining-route replanning that preserves vehicle state (docs/simulation.md).

Policy:
- Preserved: the clock, every completed stop, each vehicle's position. A vehicle that is on an
  edge finishes that edge; its new plan starts at the edge's target node.
- Scope: each vehicle keeps its own remaining customers (goods are already on board, so
  customers are not moved between vehicles). Their visiting order and all paths are recomputed
  on the CURRENT road conditions (closures, traffic, incidents).
- Order: exact (all permutations) for up to EXACT_LIMIT stops, otherwise cheapest insertion
  followed by first-improvement 2-opt and relocate; both on directed shortest-path times.
- Unreachable stops are reported as `unserved` for that vehicle, never given an artificial
  cost. If the end depot is unreachable the vehicle is reported, not silently re-routed.
- Metrics: latency is measured wall time; disruption compares old and new remaining plans.
"""

from __future__ import annotations

import itertools
import math
import time
from typing import Any

from trafiqon.routing.shortest_path import dijkstra
from trafiqon.simulation.engine import Leg, Simulation, SimulationError, VehicleState, VehicleStatus

EXACT_LIMIT = 7


def _paths(sim: Simulation, sources: list[str]) -> dict[str, Any]:
    return {s: dijkstra(sim.graph, s) for s in dict.fromkeys(sources)}


def _order_cost(order: list[str], origin: str, end: str, loc: dict[str, str], trees) -> float:
    cost, at = 0.0, origin
    for stop in order:
        t = trees[at].time.get(loc[stop])
        if t is None:
            return math.inf
        cost, at = cost + t, loc[stop]
    t = trees[at].time.get(end)
    return math.inf if t is None else cost + t


def _best_order(stops: list[str], origin: str, end: str, loc, trees) -> list[str]:
    if not stops:
        return []
    if len(stops) <= EXACT_LIMIT:
        best, best_cost = None, math.inf
        for perm in itertools.permutations(sorted(stops)):  # sorted: deterministic tie-breaking
            c = _order_cost(list(perm), origin, end, loc, trees)
            if c < best_cost - 1e-12:
                best, best_cost = list(perm), c
        return best if best is not None else []
    order: list[str] = []
    for s in sorted(stops):
        cands = [
            (_order_cost([*order[:i], s, *order[i:]], origin, end, loc, trees), i)
            for i in range(len(order) + 1)
        ]
        c, i = min(cands)
        if math.isfinite(c):
            order.insert(i, s)
    improved = True
    while improved:
        improved = False
        base = _order_cost(order, origin, end, loc, trees)
        for i, j in itertools.combinations(range(len(order)), 2):
            cand = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
            if _order_cost(cand, origin, end, loc, trees) < base - 1e-9:
                order, improved = cand, True
                break
    return order


def replan(sim: Simulation) -> dict[str, Any]:
    """Replan every unfinished vehicle's remaining journey in place. Returns metrics."""
    started = time.perf_counter()
    customers = {c.id: c.node_id for c in sim.scenario.customers}
    per_vehicle: list[dict[str, Any]] = []
    for vid in sorted(sim.vehicles):
        v: VehicleState = sim.vehicles[vid]
        if v.status in (VehicleStatus.FINISHED, VehicleStatus.IDLE) and not v.unserved:
            continue
        origin = sim.graph.edges[v.on_edge].target if v.on_edge else v.node
        old_stops = v.remaining_stops()
        old_edges = set(v.remaining_edges())
        stops = list(dict.fromkeys(old_stops + v.unserved))  # retry previously unserved stops
        trees = _paths(sim, [origin, *(customers[s] for s in stops)])
        end_reachable = v.end_node in trees[origin].time
        legs: list[Leg] = []
        if end_reachable:
            reachable = [
                s
                for s in stops
                if customers[s] in trees[origin].time and v.end_node in trees[customers[s]].time
            ]
            order = _best_order(reachable, origin, v.end_node, customers, trees)
            at = origin
            for stop in [*order, None]:
                target = customers[stop] if stop else v.end_node
                path = trees[at].path_to(target)
                if path is None:  # pragma: no cover - excluded by the reachability filter
                    raise SimulationError(f"internal: no path {at}->{target} after ordering")
                legs.append(Leg(stop, target, list(path.edge_ids)))
                at = target
        else:
            # Stranded: the end depot cannot be reached from here under current conditions.
            # Stops at the vehicle's own node are still served; everything else is reported.
            order = [s for s in stops if customers[s] == origin]
            legs = [Leg(s, origin, []) for s in order]
        unserved = [s for s in stops if s not in order]
        v.legs, v.edge_index, v.unserved = legs, 0, unserved
        if v.on_edge is None:
            v.node = origin
        if not end_reachable and v.on_edge is None and not legs:
            v.status = VehicleStatus.BLOCKED  # stranded: reported, waits for roads to reopen
        elif v.status in (VehicleStatus.BLOCKED, VehicleStatus.FINISHED):
            v.status = VehicleStatus.EN_ROUTE
        new_edges = set(v.remaining_edges())
        per_vehicle.append(
            {
                "vehicle_id": vid,
                "origin_node": origin,
                "on_edge": v.on_edge,
                "old_stops": old_stops,
                "new_stops": order,
                "unserved": unserved,
                "end_depot_reachable": end_reachable,
                "stops_reordered": sum(
                    1 for a, b in itertools.zip_longest(old_stops, order) if a != b
                ),
                "edges_changed": len(old_edges ^ new_edges),
                "remaining_time_min": _order_cost(order, origin, v.end_node, customers, trees)
                if end_reachable
                else None,
            }
        )
    latency_ms = (time.perf_counter() - started) * 1000
    sim.plan_version += 1
    result = {
        "plan_version": sim.plan_version,
        "time": sim.time,
        "tick": sim.tick,
        "latency_ms": latency_ms,  # measured
        "vehicles": per_vehicle,
        "stops_reordered": sum(p["stops_reordered"] for p in per_vehicle),  # derived
        "edges_changed": sum(p["edges_changed"] for p in per_vehicle),  # derived
        "unserved": sorted(s for p in per_vehicle for s in p["unserved"]),
        "quantity_kinds": {
            "latency_ms": "measured",
            "stops_reordered": "derived",
            "edges_changed": "derived",
            "remaining_time_min": "derived",
        },
    }
    sim.last_replan = result
    sim._log(
        "replanned",
        {
            "plan_version": sim.plan_version,
            "unserved": result["unserved"],
            "latency_ms": round(latency_ms, 3),
        },
    )
    return result
