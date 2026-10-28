"""Build initial simulation plans from evaluated solutions (the shared evaluator's legs)."""

from __future__ import annotations

from typing import Any

from trafiqon.domain.models import Scenario
from trafiqon.domain.solution import Solution, VehicleRoute
from trafiqon.optimization.problem import RoutingProblem, cheapest_insertion
from trafiqon.routing.cost_matrix import build_scenario_matrix
from trafiqon.routing.evaluation import evaluate_solution
from trafiqon.simulation.engine import Leg, PlannedRoute, SimulationError


def routes_from_solution(scenario: Scenario, solution: Solution) -> list[PlannedRoute]:
    """Plan = exactly the evaluator's leg paths for a FEASIBLE solution."""
    evaluation = evaluate_solution(scenario, solution)
    if not evaluation.feasible:
        codes = sorted({v.code for v in evaluation.violations})
        raise SimulationError(f"cannot simulate an infeasible solution ({', '.join(codes)})")
    depots = {d.id: d.node_id for d in scenario.depots}
    out = []
    for route, ev in zip(solution.routes, evaluation.routes, strict=True):
        stops: list[str | None] = [*route.customer_ids, None]
        legs = []
        for stop, leg in zip(stops, ev.legs, strict=True):
            target = depots[route.end_depot_id] if stop is None else leg.target_node
            legs.append(Leg(stop, target, list(leg.edge_ids)))
        out.append(PlannedRoute(route.vehicle_id, route.start_depot_id, route.end_depot_id, legs))
    return out


def solution_from_stored(stored: dict[str, Any]) -> Solution:
    """Rebuild a Solution from run_results.solution (as written by the worker)."""
    return Solution(
        tuple(
            VehicleRoute(
                r["vehicle_id"], tuple(r["customer_ids"]), r["start_depot_id"], r["end_depot_id"]
            )
            for r in stored["routes"]
        )
    )


def construction_routes(scenario: Scenario) -> list[PlannedRoute]:
    """Deterministic cheapest-insertion plan, for simulating without an optimization run."""
    problem = RoutingProblem(scenario, build_scenario_matrix(scenario))
    routes = cheapest_insertion(problem)
    if problem.overload(routes):
        raise SimulationError(
            "construction could not find a capacity-feasible plan; run an optimizer"
        )
    return routes_from_solution(scenario, problem.to_solution(routes))
