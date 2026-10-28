"""The single authoritative objective and feasibility evaluator.

Every algorithm's output and every displayed objective value must come from
`evaluate_solution`. Objective f(S) = sum of `current_time` over every traversed edge of
every route, under the scenario graph's current conditions. Distance is tracked separately.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from trafiqon.domain.models import Edge, Graph, Scenario
from trafiqon.domain.solution import Solution, VehicleRoute
from trafiqon.routing.cost_matrix import CostMatrix, build_scenario_matrix
from trafiqon.routing.shortest_path import Path, shortest_path

EVALUATOR_VERSION = "1"


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    message: str
    vehicle_id: str | None = None
    customer_id: str | None = None


@dataclass(frozen=True, slots=True)
class LegEvaluation:
    source_node: str
    target_node: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    travel_time: float | None  # None when the leg is unreachable or invalid
    distance: float | None


@dataclass(frozen=True, slots=True)
class RouteEvaluation:
    vehicle_id: str
    customer_ids: tuple[str, ...]
    load: int
    capacity: int | None
    legs: tuple[LegEvaluation, ...]
    travel_time: float | None  # None unless every leg is valid
    distance: float | None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    feasible: bool
    objective: float | None  # total travel time; None if any leg is unreachable/invalid
    total_distance: float | None
    routes: tuple[RouteEvaluation, ...]
    violations: tuple[Violation, ...]
    evaluator_version: str = EVALUATOR_VERSION


def evaluate_solution(
    scenario: Scenario, solution: Solution, matrix: CostMatrix | None = None
) -> EvaluationResult:
    """Evaluate `solution` against `scenario`. `matrix`, if given, must be built from
    `scenario.graph` (it is a cache of shortest-path legs, not an independent cost source)."""
    violations: list[Violation] = []
    matrix = matrix or build_scenario_matrix(scenario)
    customers = {c.id: c for c in scenario.customers}
    vehicles = {v.id: v for v in scenario.vehicles}
    depots = {d.id: d for d in scenario.depots}

    visits = Counter(cid for route in solution.routes for cid in route.customer_ids)
    for cid, count in sorted(visits.items()):
        if cid not in customers:
            violations.append(
                Violation("unknown_customer", f"unknown customer {cid!r}", customer_id=cid)
            )
        elif count > 1:
            violations.append(
                Violation(
                    "duplicate_customer", f"customer {cid!r} served {count} times", customer_id=cid
                )
            )
    for cid in customers:
        if cid not in visits:
            violations.append(
                Violation("missing_customer", f"customer {cid!r} not served", customer_id=cid)
            )

    for vid, count in Counter(r.vehicle_id for r in solution.routes).items():
        if count > 1:
            violations.append(
                Violation(
                    "duplicate_vehicle", f"vehicle {vid!r} has {count} routes", vehicle_id=vid
                )
            )

    route_results: list[RouteEvaluation] = []
    all_legs_valid = True
    for route in solution.routes:
        result, route_violations = _evaluate_route(
            scenario, route, matrix, customers, vehicles, depots
        )
        violations.extend(route_violations)
        route_results.append(result)
        if result.travel_time is None:
            all_legs_valid = False

    objective = total_distance = None
    if all_legs_valid:
        objective = math.fsum(r.travel_time for r in route_results)  # type: ignore[misc]
        total_distance = math.fsum(r.distance for r in route_results)  # type: ignore[misc]
    return EvaluationResult(
        feasible=not violations,
        objective=objective,
        total_distance=total_distance,
        routes=tuple(route_results),
        violations=tuple(violations),
    )


def _evaluate_route(scenario, route: VehicleRoute, matrix, customers, vehicles, depots):
    violations: list[Violation] = []
    vid = route.vehicle_id
    vehicle = vehicles.get(vid)
    if vehicle is None:
        violations.append(Violation("unknown_vehicle", f"unknown vehicle {vid!r}", vehicle_id=vid))
    else:
        if route.start_depot_id != vehicle.start_depot_id:
            violations.append(
                Violation(
                    "invalid_start_depot",
                    f"vehicle {vid!r} must start at {vehicle.start_depot_id!r}, "
                    f"not {route.start_depot_id!r}",
                    vehicle_id=vid,
                )
            )
        if route.end_depot_id not in vehicle.allowed_end_depots:
            violations.append(
                Violation(
                    "invalid_end_depot",
                    f"vehicle {vid!r} cannot end at {route.end_depot_id!r}",
                    vehicle_id=vid,
                )
            )

    load = sum(customers[c].demand for c in route.customer_ids if c in customers)
    capacity = vehicle.capacity if vehicle else None
    if capacity is not None and load > capacity:
        violations.append(
            Violation(
                "capacity_exceeded",
                f"vehicle {vid!r} load {load} > capacity {capacity}",
                vehicle_id=vid,
            )
        )

    stop_nodes: list[str | None] = [
        depots[route.start_depot_id].node_id if route.start_depot_id in depots else None
    ]
    stop_nodes += [customers[c].node_id if c in customers else None for c in route.customer_ids]
    stop_nodes.append(depots[route.end_depot_id].node_id if route.end_depot_id in depots else None)
    for depot_id in (route.start_depot_id, route.end_depot_id):
        if depot_id not in depots:
            violations.append(
                Violation("unknown_depot", f"unknown depot {depot_id!r}", vehicle_id=vid)
            )

    n_legs = len(stop_nodes) - 1
    if route.legs is not None and len(route.legs) != n_legs:
        violations.append(
            Violation(
                "leg_count_mismatch",
                f"vehicle {vid!r} has {len(route.legs)} explicit legs, expected {n_legs}",
                vehicle_id=vid,
            )
        )
        legs_valid = False
        legs: list[LegEvaluation] = []
    else:
        legs = []
        legs_valid = True
        for k in range(n_legs):
            a, b = stop_nodes[k], stop_nodes[k + 1]
            if a is None or b is None:
                legs_valid = False
                continue
            if route.legs is None:
                leg, leg_violation = _shortest_leg(scenario, matrix, a, b, vid)
            else:
                leg, leg_violation = evaluate_leg(scenario.graph, route.legs[k], a, b, vid)
            if leg_violation:
                violations.append(leg_violation)
            legs.append(leg)
            if leg.travel_time is None:
                legs_valid = False

    travel_time = distance = None
    if legs_valid:
        travel_time = math.fsum(leg.travel_time for leg in legs)  # type: ignore[misc]
        distance = math.fsum(leg.distance for leg in legs)  # type: ignore[misc]
    return (
        RouteEvaluation(
            vid, route.customer_ids, load, capacity, tuple(legs), travel_time, distance
        ),
        violations,
    )


def _from_path(path: Path) -> LegEvaluation:
    return LegEvaluation(
        path.source, path.target, path.node_ids, path.edge_ids, path.travel_time, path.distance
    )


def _shortest_leg(scenario: Scenario, matrix: CostMatrix, a: str, b: str, vid: str):
    path = matrix.leg(a, b)
    if path is None and (a not in matrix.index or b not in matrix.index):
        path = shortest_path(scenario.graph, a, b)
    if path is None:
        return (
            LegEvaluation(a, b, (), (), None, None),
            Violation("unreachable_leg", f"no open path {a!r} -> {b!r}", vehicle_id=vid),
        )
    return _from_path(path), None


def evaluate_leg(
    graph: Graph, edge_ids: tuple[str, ...], a: str, b: str, vid: str | None = None
) -> tuple[LegEvaluation, Violation | None]:
    """Validate and cost one explicit edge path from node `a` to node `b`."""
    invalid = LegEvaluation(a, b, (), tuple(edge_ids), None, None)
    edges: list[Edge] = []
    for eid in edge_ids:
        edge = graph.edges.get(eid)
        if edge is None:
            return invalid, Violation("unknown_edge", f"unknown edge {eid!r}", vehicle_id=vid)
        if edge.closed:
            return invalid, Violation("closed_edge", f"edge {eid!r} is closed", vehicle_id=vid)
        edges.append(edge)
    node = a
    for edge in edges:
        if edge.source != node:
            return invalid, Violation(
                "discontinuous_leg",
                f"edge {edge.id!r} starts at {edge.source!r}, expected {node!r}",
                vehicle_id=vid,
            )
        node = edge.target
    if node != b:
        return invalid, Violation(
            "discontinuous_leg", f"leg ends at {node!r}, expected {b!r}", vehicle_id=vid
        )
    return (
        LegEvaluation(
            a,
            b,
            (a, *(e.target for e in edges)),
            tuple(edge_ids),
            math.fsum(e.current_time for e in edges),
            math.fsum(e.distance for e in edges),
        ),
        None,
    )
