"""Pydantic request/response schemas for /api/v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(Schema):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(Schema):
    error: ErrorBody


class DependencyStatus(Schema):
    status: Literal["ok", "unavailable", "not_configured"]


class HealthResponse(Schema):
    status: Literal["ok"]
    version: str
    api_version: Literal["v1"]
    dependencies: dict[str, DependencyStatus]


class NodeOut(Schema):
    id: str
    x: float | None
    y: float | None
    label: str | None


class EdgeOut(Schema):
    id: str
    source: str
    target: str
    distance: float = Field(description="km")
    base_time: float = Field(description="minutes, free-flow")
    current_time: float = Field(description="minutes, used for routing")
    closed: bool
    road_class: str | None
    capacity: float | None
    congestion: float | None


class GraphOut(Schema):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class DepotOut(Schema):
    id: str
    node_id: str


class CustomerOut(Schema):
    id: str
    node_id: str
    demand: int


class VehicleOut(Schema):
    id: str
    capacity: int
    start_depot_id: str
    end_depot_ids: list[str]


class ScenarioOut(Schema):
    id: str
    name: str
    description: str
    synthetic: bool
    settings: dict[str, Any]
    graph: GraphOut
    depots: list[DepotOut]
    customers: list[CustomerOut]
    vehicles: list[VehicleOut]


class ScenarioSummary(Schema):
    id: str
    name: str
    description: str
    synthetic: bool
    node_count: int
    edge_count: int
    customer_count: int
    vehicle_count: int


class ShortestPathRequest(Schema):
    scenario_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100, description="node id")
    target: str = Field(min_length=1, max_length=100, description="node id")
    algorithm: Literal["dijkstra", "astar"] = "dijkstra"


class PathOut(Schema):
    node_ids: list[str]
    edge_ids: list[str]
    travel_time: float = Field(description="minutes, from the shared evaluator")
    distance: float = Field(description="km, from the shared evaluator")


class ShortestPathResponse(Schema):
    scenario_id: str
    algorithm: Literal["dijkstra", "astar"]
    source: str
    target: str
    reachable: bool
    path: PathOut | None
    expanded_nodes: int
    evaluator_version: str
