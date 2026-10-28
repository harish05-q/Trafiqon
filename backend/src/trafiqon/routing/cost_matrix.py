"""Directed location-to-location cost matrix built from shortest paths.

Locations are the distinct graph nodes of all depots and customers. Unreachable pairs are
recorded explicitly in `reachable` (their time/distance entries are NaN, never a big-M).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trafiqon.domain.models import Graph, Scenario
from trafiqon.routing.shortest_path import Path, dijkstra


@dataclass(frozen=True, slots=True)
class CostMatrix:
    node_ids: tuple[str, ...]
    index: dict[str, int]
    time: np.ndarray  # float64 [n, n]; NaN where unreachable
    distance: np.ndarray  # float64 [n, n]; NaN where unreachable
    reachable: np.ndarray  # bool [n, n]
    paths: dict[tuple[str, str], Path]  # edge-level path per reachable ordered pair

    def leg(self, source: str, target: str) -> Path | None:
        return self.paths.get((source, target))

    def unreachable_pairs(self) -> list[tuple[str, str]]:
        rows, cols = np.nonzero(~self.reachable)
        return [(self.node_ids[i], self.node_ids[j]) for i, j in zip(rows, cols, strict=True)]


def build_cost_matrix(graph: Graph, node_ids: list[str] | tuple[str, ...]) -> CostMatrix:
    ordered = tuple(dict.fromkeys(node_ids))  # dedupe, keep order
    n = len(ordered)
    index = {node: i for i, node in enumerate(ordered)}
    time = np.full((n, n), np.nan)
    distance = np.full((n, n), np.nan)
    reachable = np.zeros((n, n), dtype=bool)
    paths: dict[tuple[str, str], Path] = {}
    for i, source in enumerate(ordered):
        tree = dijkstra(graph, source)
        for j, target in enumerate(ordered):
            path = tree.path_to(target)
            if path is None:
                continue
            paths[(source, target)] = path
            time[i, j] = path.travel_time
            distance[i, j] = path.distance
            reachable[i, j] = True
    return CostMatrix(ordered, index, time, distance, reachable, paths)


def scenario_locations(scenario: Scenario) -> tuple[str, ...]:
    """Depot nodes first, then customer nodes, in declaration order."""
    nodes = [d.node_id for d in scenario.depots] + [c.node_id for c in scenario.customers]
    return tuple(dict.fromkeys(nodes))


def build_scenario_matrix(scenario: Scenario) -> CostMatrix:
    return build_cost_matrix(scenario.graph, scenario_locations(scenario))


@dataclass(frozen=True, slots=True)
class ReachabilityIssue:
    code: str
    message: str
    ref: str


def check_reachability(
    scenario: Scenario, matrix: CostMatrix | None = None
) -> list[ReachabilityIssue]:
    """Report customers that no vehicle can serve under current conditions.

    A customer is servable if some vehicle can reach it from its start depot and return
    from it to one of its allowed end depots. Pairwise customer-to-customer gaps are not
    errors (a solution can avoid them) and are exposed by `CostMatrix.unreachable_pairs`.
    """
    matrix = matrix or build_scenario_matrix(scenario)
    depot_node = {d.id: d.node_id for d in scenario.depots}
    issues: list[ReachabilityIssue] = []
    for customer in scenario.customers:
        big_enough = [v for v in scenario.vehicles if v.capacity >= customer.demand]
        if not big_enough:
            continue  # a capacity problem, reported by validate_scenario, not reachability
        servable = any(
            matrix.leg(depot_node[v.start_depot_id], customer.node_id) is not None
            and any(
                matrix.leg(customer.node_id, depot_node[end]) is not None
                for end in v.allowed_end_depots
            )
            for v in big_enough
        )
        if not servable:
            issues.append(
                ReachabilityIssue(
                    "customer_unreachable",
                    f"no vehicle can travel depot -> {customer.id!r} -> depot over open roads",
                    customer.id,
                )
            )
    return issues
