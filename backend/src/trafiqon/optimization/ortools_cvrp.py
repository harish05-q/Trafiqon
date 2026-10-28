"""OR-Tools CVRP reference baseline on the directed shortest-path cost matrix.

Modelling:
- Model nodes: one per depot, one per customer, plus one dummy end per vehicle that has
  several allowed end depots (arc cost to it = cheapest allowed end depot from that node).
- Arc costs are travel times scaled to integers (`cost_scale` units per minute).
- Unreachable arcs are REMOVED from the model (NextVar domain), not given a big-M cost.
- Capacity: one dimension with per-vehicle capacities.
The reported objective is the shared evaluator's value for the extracted routes, not the
solver's integer cost. A time-limited metaheuristic result is never labelled optimal; only a
ROUTING_OPTIMAL status (optimal w.r.t. the integer-scaled costs) is reported as proven.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from trafiqon.optimization.contract import (
    AlgorithmInput,
    AlgorithmResult,
    ConfigError,
    HistoryPoint,
    Optimality,
    ProgressEvent,
    Stopwatch,
    TerminationReason,
    check_number,
    finalize,
    merge_config,
)
from trafiqon.optimization.problem import RoutingProblem, infeasibility_reasons

FIRST_SOLUTION = dict(routing_enums_pb2.FirstSolutionStrategy.Value.items())
METAHEURISTICS = dict(routing_enums_pb2.LocalSearchMetaheuristic.Value.items())
STATUS_NAMES = {v: k for k, v in routing_enums_pb2.RoutingSearchStatus.Value.items()}


class OrToolsCvrp:
    id = "ortools_cvrp"
    version = "1"
    defaults: Mapping[str, Any] = {
        "time_limit_s": 2.0,
        "first_solution_strategy": "PATH_CHEAPEST_ARC",
        "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
        "solution_limit": None,
        "cost_scale": 1000,
    }

    def resolve_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        cfg = merge_config(self.defaults, config, self.id)
        check_number(cfg, "time_limit_s", minimum=0.01, maximum=600)
        check_number(cfg, "solution_limit", minimum=1, integer=True, allow_none=True)
        check_number(cfg, "cost_scale", minimum=1, maximum=1_000_000, integer=True)
        if cfg["first_solution_strategy"] not in FIRST_SOLUTION:
            raise ConfigError(f"unknown first_solution_strategy {cfg['first_solution_strategy']!r}")
        if cfg["local_search_metaheuristic"] not in METAHEURISTICS:
            raise ConfigError(
                f"unknown local_search_metaheuristic {cfg['local_search_metaheuristic']!r}"
            )
        return cfg

    def run(self, inp: AlgorithmInput) -> AlgorithmResult:
        clock = Stopwatch()
        cfg = self.resolve_config(inp.config)
        matrix = inp.cost_matrix()
        problem = RoutingProblem(inp.scenario, matrix)
        common: dict[str, Any] = {"seed": None}  # OR-Tools routing search takes no seed

        reasons = infeasibility_reasons(inp.scenario, matrix)
        if reasons:
            return finalize(
                self,
                inp,
                cfg,
                matrix,
                None,
                iterations=0,
                evaluations=None,
                elapsed_s=clock.elapsed(),
                time_to_first_feasible_s=None,
                termination_reason=TerminationReason.INFEASIBLE_SCENARIO,
                diagnostics={"infeasibility": reasons},
                **common,
            )
        if inp.cancel.is_cancelled():
            return finalize(
                self,
                inp,
                cfg,
                matrix,
                None,
                iterations=0,
                evaluations=None,
                elapsed_s=clock.elapsed(),
                time_to_first_feasible_s=None,
                termination_reason=TerminationReason.CANCELLED,
                **common,
            )

        n_depots = len(inp.scenario.depots)
        depot_pos = {d.id: k for k, d in enumerate(inp.scenario.depots)}
        depot_loc = [matrix.index[d.node_id] for d in inp.scenario.depots]
        n_cust = problem.n_customers
        # Model node -> matrix location (None for dummy ends); dummy end -> allowed matrix idx.
        loc: list[int | None] = [*depot_loc, *problem.customer_loc.tolist()]
        dummy_targets: dict[int, list[int]] = {}
        starts, ends = [], []
        for spec in problem.vehicles:
            starts.append(depot_pos[spec.start_depot_id])
            if len(spec.ends) == 1:
                ends.append(depot_pos[spec.ends[0][0]])
            else:
                dummy_targets[len(loc)] = [idx for _, idx in spec.ends]
                ends.append(len(loc))
                loc.append(None)

        t = problem.time
        scale = cfg["cost_scale"]

        def leg_time(i: int, j: int) -> float:
            if i == j:
                return 0.0
            if j in dummy_targets:
                li = loc[i]
                return min(t[li, e] for e in dummy_targets[j]) if li is not None else math.inf
            li, lj = loc[i], loc[j]
            if li is None or lj is None:
                return math.inf
            return float(t[li, lj])

        n_model = len(loc)
        cost_table = [[leg_time(i, j) for j in range(n_model)] for i in range(n_model)]
        int_table = [
            [round(c * scale) if math.isfinite(c) else 0 for c in row] for row in cost_table
        ]  # 0 is never used: unreachable arcs are removed below.

        manager = pywrapcp.RoutingIndexManager(n_model, problem.n_vehicles, starts, ends)
        routing = pywrapcp.RoutingModel(manager)

        def transit(i: int, j: int) -> int:
            return int_table[manager.IndexToNode(i)][manager.IndexToNode(j)]

        cb = routing.RegisterTransitCallback(transit)
        routing.SetArcCostEvaluatorOfAllVehicles(cb)
        demand = [0] * n_depots + problem.demand.tolist() + [0] * (n_model - n_depots - n_cust)
        dcb = routing.RegisterUnaryTransitCallback(lambda i: demand[manager.IndexToNode(i)])
        routing.AddDimensionWithVehicleCapacity(
            dcb, 0, [s.capacity for s in problem.vehicles], True, "Capacity"
        )

        removed = 0
        customer_nodes = range(n_depots, n_depots + n_cust)
        for c in customer_nodes:
            ci = manager.NodeToIndex(c)
            for c2 in customer_nodes:
                if c2 != c and not math.isfinite(cost_table[c][c2]):
                    routing.NextVar(ci).RemoveValue(manager.NodeToIndex(c2))
                    removed += 1
            for v in range(problem.n_vehicles):
                if not math.isfinite(cost_table[starts[v]][c]):
                    routing.NextVar(routing.Start(v)).RemoveValue(ci)
                    removed += 1
                if not math.isfinite(cost_table[c][ends[v]]):
                    routing.NextVar(ci).RemoveValue(routing.End(v))
                    removed += 1

        history: list[HistoryPoint] = []
        state: dict[str, Any] = {"best": None, "first": None, "count": 0}

        def on_solution() -> None:
            state["count"] += 1
            value = routing.CostVar().Value() / scale
            elapsed = clock.elapsed()
            if state["first"] is None:
                state["first"] = elapsed
            if state["best"] is None or value < state["best"]:
                state["best"] = value
            history.append(HistoryPoint(state["count"], None, elapsed, value, state["best"]))
            if inp.progress:
                inp.progress(
                    ProgressEvent(
                        iteration=state["count"],
                        evaluations=None,
                        elapsed_s=elapsed,
                        best_objective=state["best"],
                        current_objective=value,
                        has_feasible=True,
                        message="solver solution (integer-scaled cost / scale)",
                    )
                )

        routing.AddAtSolutionCallback(on_solution)
        routing.AddSearchMonitor(routing.solver().CustomLimit(inp.cancel.is_cancelled))

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = FIRST_SOLUTION[cfg["first_solution_strategy"]]
        params.local_search_metaheuristic = METAHEURISTICS[cfg["local_search_metaheuristic"]]
        params.time_limit.FromMilliseconds(int(cfg["time_limit_s"] * 1000))
        if cfg["solution_limit"] is not None:
            params.solution_limit = cfg["solution_limit"]

        search_start = clock.elapsed()
        assignment = routing.SolveWithParameters(params)
        search_s = clock.elapsed() - search_start
        status = STATUS_NAMES.get(routing.status(), str(routing.status()))

        routes = None
        if assignment is not None:
            routes = []
            for v in range(problem.n_vehicles):
                seq, index = [], routing.Start(v)
                while not routing.IsEnd(index):
                    node = manager.IndexToNode(index)
                    if n_depots <= node < n_depots + n_cust:
                        seq.append(node - n_depots)
                    index = assignment.Value(routing.NextVar(index))
                routes.append(seq)

        if inp.cancel.is_cancelled():
            reason = TerminationReason.CANCELLED
        elif assignment is None:
            reason = TerminationReason.NO_SOLUTION_FOUND
        elif search_s >= cfg["time_limit_s"] * 0.95:
            reason = TerminationReason.TIME_LIMIT
        else:
            reason = TerminationReason.SOLVER_FINISHED
        optimality = (
            Optimality.PROVEN_OPTIMAL if status == "ROUTING_OPTIMAL" else Optimality.NOT_PROVEN
        )
        return finalize(
            self,
            inp,
            cfg,
            matrix,
            problem.to_solution(routes) if routes is not None else None,
            iterations=state["count"],
            evaluations=None,
            elapsed_s=clock.elapsed(),
            time_to_first_feasible_s=state["first"],
            termination_reason=reason,
            optimality=optimality,
            history=tuple(history),
            diagnostics={
                "solver_status": status,
                "solver_objective_scaled": assignment.ObjectiveValue() if assignment else None,
                "cost_scale": scale,
                "removed_unreachable_arcs": removed,
                "solutions_found": state["count"],
                "deterministic": False,
                "note": "time-limited search; repeated runs may differ. Optimality, if "
                "reported, is w.r.t. integer-scaled costs.",
            },
            **common,
        )
