"""/api/v1 routes that need no database: built-in scenarios and shortest paths."""

from __future__ import annotations

from fastapi import APIRouter

from trafiqon.api.errors import ApiError
from trafiqon.api.schemas import (
    ErrorResponse,
    PathOut,
    ScenarioOut,
    ScenarioSummary,
    ShortestPathRequest,
    ShortestPathResponse,
)
from trafiqon.domain.models import Scenario
from trafiqon.domain.serialization import scenario_to_dict
from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin
from trafiqon.routing import astar, dijkstra, evaluate_leg
from trafiqon.routing.evaluation import EVALUATOR_VERSION

router = APIRouter(prefix="/api/v1")
NOT_FOUND = {404: {"model": ErrorResponse}}


def _get_builtin(scenario_id: str) -> Scenario:
    if scenario_id not in BUILTIN_SCENARIOS:
        raise ApiError(404, "scenario_not_found", f"unknown built-in scenario {scenario_id!r}")
    return load_builtin(scenario_id)


@router.get("/scenarios/builtin", response_model=list[ScenarioSummary])
def list_builtin() -> list[ScenarioSummary]:
    out = []
    for scenario_id in BUILTIN_SCENARIOS:
        s = load_builtin(scenario_id)
        out.append(
            ScenarioSummary(
                id=s.id,
                name=s.name,
                description=s.description,
                synthetic=s.synthetic,
                node_count=len(s.graph.nodes),
                edge_count=len(s.graph.edges),
                customer_count=len(s.customers),
                vehicle_count=len(s.vehicles),
            )
        )
    return out


@router.get("/scenarios/builtin/{scenario_id}", response_model=ScenarioOut, responses=NOT_FOUND)
def get_builtin(scenario_id: str) -> ScenarioOut:
    return ScenarioOut.model_validate(scenario_to_dict(_get_builtin(scenario_id)))


@router.post(
    "/routing/shortest-path",
    response_model=ShortestPathResponse,
    responses={**NOT_FOUND, 422: {"model": ErrorResponse}},
)
def shortest_path(req: ShortestPathRequest) -> ShortestPathResponse:
    scenario = _get_builtin(req.scenario_id)
    graph = scenario.graph
    for field in ("source", "target"):
        node = getattr(req, field)
        if not graph.has_node(node):
            raise ApiError(422, "unknown_node", f"{field} node {node!r} not in scenario")

    if req.algorithm == "astar":
        path, stats = astar(graph, req.source, req.target)
    else:
        tree = dijkstra(graph, req.source, req.target)
        path, stats = tree.path_to(req.target), tree.stats

    path_out = None
    if path is not None:
        # Re-validate and cost the path with the shared evaluator; never trust the search.
        leg, violation = evaluate_leg(graph, path.edge_ids, req.source, req.target)
        if violation is not None or leg.travel_time is None or leg.distance is None:
            raise ApiError(500, "invalid_path", "search produced a path the evaluator rejected")
        path_out = PathOut(
            node_ids=list(leg.node_ids),
            edge_ids=list(leg.edge_ids),
            travel_time=leg.travel_time,
            distance=leg.distance,
        )
    return ShortestPathResponse(
        scenario_id=scenario.id,
        algorithm=req.algorithm,
        source=req.source,
        target=req.target,
        reachable=path_out is not None,
        path=path_out,
        expanded_nodes=stats.expanded,
        evaluator_version=EVALUATOR_VERSION,
    )
