"""AlgorithmResult -> JSON-safe dicts for run_results. Non-finite floats become null."""

from __future__ import annotations

import math
from typing import Any

from trafiqon.optimization import AlgorithmResult
from trafiqon.routing.evaluation import EvaluationResult

MAX_HISTORY_POINTS = 500


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(v) for v in value]
    return value


def evaluation_to_dict(ev: EvaluationResult) -> dict[str, Any]:
    return {
        "feasible": ev.feasible,
        "objective": ev.objective,
        "total_distance": ev.total_distance,
        "evaluator_version": ev.evaluator_version,
        "violations": [
            {
                "code": v.code,
                "message": v.message,
                "vehicle_id": v.vehicle_id,
                "customer_id": v.customer_id,
            }
            for v in ev.violations
        ],
        "routes": [
            {
                "vehicle_id": r.vehicle_id,
                "customer_ids": list(r.customer_ids),
                "load": r.load,
                "capacity": r.capacity,
                "travel_time": r.travel_time,
                "distance": r.distance,
                "legs": [
                    {
                        "source_node": leg.source_node,
                        "target_node": leg.target_node,
                        "node_ids": list(leg.node_ids),
                        "edge_ids": list(leg.edge_ids),
                        "travel_time": leg.travel_time,
                        "distance": leg.distance,
                    }
                    for leg in r.legs
                ],
            }
            for r in ev.routes
        ],
    }


def downsample(points: list[Any], limit: int = MAX_HISTORY_POINTS) -> list[Any]:
    """Keep first, last and evenly spaced points in between."""
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def result_to_row(result: AlgorithmResult, software: dict[str, str]) -> dict[str, Any]:
    history = [
        {
            "iteration": h.iteration,
            "evaluations": h.evaluations,
            "elapsed_s": h.elapsed_s,
            "current_objective": h.current_objective,
            "best_objective": h.best_objective,
        }
        for h in result.history
    ]
    solution = None
    if result.solution is not None:
        solution = {
            "routes": [
                {
                    "vehicle_id": r.vehicle_id,
                    "customer_ids": list(r.customer_ids),
                    "start_depot_id": r.start_depot_id,
                    "end_depot_id": r.end_depot_id,
                }
                for r in result.solution.routes
            ]
        }
    return json_safe(
        {
            "feasible": result.feasible,
            "objective": result.objective,
            "total_distance": result.evaluation.total_distance if result.evaluation else None,
            "solution": solution,
            "evaluation": evaluation_to_dict(result.evaluation) if result.evaluation else None,
            "iterations": result.iterations,
            "evaluations": result.evaluations,
            "elapsed_s": result.elapsed_s,
            "time_to_first_feasible_s": result.time_to_first_feasible_s,
            "termination_reason": result.termination_reason.value,
            "optimality": result.optimality.value,
            "seed": result.seed,
            "history": downsample(history),
            "diagnostics": {
                **result.diagnostics,
                "software": software,
                "history_points_total": len(history),
            },
        }
    )
