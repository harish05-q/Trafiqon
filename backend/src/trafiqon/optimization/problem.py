"""Index-based CVRP view of a scenario, shared by SA and the QPSO-inspired optimizer.

A candidate is `routes: list[list[int]]`, one customer-index list per vehicle (in
`scenario.vehicles` order). Costs come from the shortest-path cost matrix; unreachable legs
are +inf INTERNALLY so searches can reject them. Such a cost is never reported: results are
always re-scored by the shared evaluator (see `contract.finalize`).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np

from trafiqon.domain.models import Scenario
from trafiqon.domain.solution import Solution, VehicleRoute
from trafiqon.domain.validation import Severity, validate_scenario
from trafiqon.routing.cost_matrix import CostMatrix, check_reachability

Routes = list[list[int]]


@dataclass(frozen=True, slots=True)
class VehicleSpec:
    id: str
    capacity: int
    start_depot_id: str
    start: int  # matrix index
    ends: tuple[tuple[str, int], ...]  # (depot id, matrix index) allowed end depots


class RoutingProblem:
    def __init__(self, scenario: Scenario, matrix: CostMatrix) -> None:
        self.scenario = scenario
        self.matrix = matrix
        depot_node = {d.id: d.node_id for d in scenario.depots}
        self.customer_ids = tuple(c.id for c in scenario.customers)
        self.customer_loc = np.array(
            [matrix.index[c.node_id] for c in scenario.customers], dtype=np.int64
        )
        self.demand = np.array([c.demand for c in scenario.customers], dtype=np.int64)
        self.vehicles = tuple(
            VehicleSpec(
                id=v.id,
                capacity=v.capacity,
                start_depot_id=v.start_depot_id,
                start=matrix.index[depot_node[v.start_depot_id]],
                ends=tuple((d, matrix.index[depot_node[d]]) for d in v.allowed_end_depots),
            )
            for v in scenario.vehicles
        )
        self.time = np.where(matrix.reachable, matrix.time, np.inf)
        self.n_customers = len(self.customer_ids)
        self.n_vehicles = len(self.vehicles)
        finite = self.time[np.isfinite(self.time)]
        self.max_leg_time = float(finite.max()) if finite.size else 0.0

    def route_cost(self, v: int, seq: list[int]) -> tuple[float, str]:
        """Travel time of vehicle `v` serving `seq`, ending at its cheapest allowed end depot.

        An empty route costs 0 (an unused vehicle is omitted from the solution).
        Returns (inf, start depot) if any leg is unreachable.
        """
        spec = self.vehicles[v]
        if not seq:
            return 0.0, spec.start_depot_id
        t = self.time
        loc = self.customer_loc
        cost = t[spec.start, loc[seq[0]]]
        for a, b in itertools.pairwise(seq):
            cost += t[loc[a], loc[b]]
        last = loc[seq[-1]]
        best_end, best_end_cost = spec.start_depot_id, math.inf
        for depot_id, idx in spec.ends:
            if t[last, idx] < best_end_cost:
                best_end, best_end_cost = depot_id, t[last, idx]
        return float(cost + best_end_cost), best_end

    def load(self, seq: list[int]) -> int:
        return int(self.demand[seq].sum()) if seq else 0

    def overload(self, routes: Routes) -> int:
        return sum(
            max(0, self.load(seq) - self.vehicles[v].capacity) for v, seq in enumerate(routes)
        )

    def total_cost(self, routes: Routes) -> float:
        return math.fsum(self.route_cost(v, seq)[0] for v, seq in enumerate(routes))

    def to_solution(self, routes: Routes) -> Solution:
        out = []
        for v, seq in enumerate(routes):
            if not seq:
                continue
            spec = self.vehicles[v]
            _, end = self.route_cost(v, seq)
            out.append(
                VehicleRoute(
                    vehicle_id=spec.id,
                    customer_ids=tuple(self.customer_ids[i] for i in seq),
                    start_depot_id=spec.start_depot_id,
                    end_depot_id=end,
                )
            )
        return Solution(tuple(out))


def infeasibility_reasons(scenario: Scenario, matrix: CostMatrix) -> list[dict[str, str]]:
    """Reasons no feasible solution can exist, found before any search. Empty = unknown."""
    reasons = [
        {"code": i.code, "message": i.message}
        for i in validate_scenario(scenario)
        if i.severity is Severity.INFEASIBLE
    ]
    reasons += [
        {"code": i.code, "message": i.message} for i in check_reachability(scenario, matrix)
    ]
    return reasons


def cheapest_insertion(problem: RoutingProblem) -> Routes:
    """Deterministic construction: customers by descending demand (ties by id), each inserted
    at the cheapest position that keeps every vehicle within capacity and every leg reachable.
    If no capacity-feasible position exists, the customer goes where overload is smallest
    (then cheapest), so the result may violate capacity; callers must check `overload`."""
    routes: Routes = [[] for _ in range(problem.n_vehicles)]
    costs = [0.0] * problem.n_vehicles
    loads = [0] * problem.n_vehicles
    order = sorted(
        range(problem.n_customers), key=lambda i: (-problem.demand[i], problem.customer_ids[i])
    )
    for c in order:
        demand = int(problem.demand[c])
        best: tuple[int, float, int, int] | None = None  # (overload, delta, vehicle, pos)
        for v, seq in enumerate(routes):
            over = max(0, loads[v] + demand - problem.vehicles[v].capacity)
            for pos in range(len(seq) + 1):
                cost, _ = problem.route_cost(v, [*seq[:pos], c, *seq[pos:]])
                if not math.isfinite(cost):
                    continue
                key = (over, cost - costs[v], v, pos)
                if best is None or key < best:
                    best = key
        if best is None:
            raise ValueError(f"customer {problem.customer_ids[c]!r} cannot be inserted anywhere")
        _, _, v, pos = best
        routes[v].insert(pos, c)
        costs[v] = problem.route_cost(v, routes[v])[0]
        loads[v] += demand
    return routes
