"""Pydantic request/response schemas for /api/v1."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

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


# --- persisted scenarios (M4) -------------------------------------------------------------


class NodeIn(Schema):
    id: str = Field(min_length=1, max_length=100)
    x: float | None = None
    y: float | None = None
    label: str | None = Field(default=None, max_length=200)


class EdgeIn(Schema):
    id: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    distance: float = Field(ge=0, allow_inf_nan=False)
    base_time: float = Field(ge=0, allow_inf_nan=False)
    current_time: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    closed: bool = False
    road_class: str | None = Field(default=None, max_length=50)
    capacity: float | None = None
    congestion: float | None = None


class GraphIn(Schema):
    nodes: list[NodeIn]
    edges: list[EdgeIn]


class VehicleIn(Schema):
    id: str = Field(min_length=1, max_length=100)
    capacity: int
    start_depot_id: str
    end_depot_ids: list[str] = []


class ScenarioData(Schema):
    """Scenario content stored in an immutable version (ids/names are set by the server)."""

    description: str = Field(default="", max_length=2000)
    synthetic: bool = True
    settings: dict[str, Any] = {}
    graph: GraphIn
    depots: list[DepotOut]
    customers: list[CustomerOut]
    vehicles: list[VehicleIn]


class ScenarioCreate(Schema):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    data: ScenarioData | None = None
    builtin_id: str | None = Field(default=None, description="copy a built-in scenario")


class ScenarioUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class VersionCreate(Schema):
    data: ScenarioData
    note: str = Field(default="", max_length=2000)


class VersionSummary(Schema):
    id: UUID
    scenario_id: UUID
    version_number: int
    fingerprint: str
    synthetic: bool
    node_count: int
    edge_count: int
    customer_count: int
    vehicle_count: int
    note: str
    created_at: datetime


class VersionOut(VersionSummary):
    data: ScenarioOut


class ScenarioRecord(Schema):
    id: UUID
    name: str
    description: str
    current_version_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ScenarioDetail(ScenarioRecord):
    versions: list[VersionSummary]


class Page[T](Schema):
    items: list[T]
    total: int
    limit: int
    offset: int


# --- runs -------------------------------------------------------------------------------


class AlgorithmInfo(Schema):
    id: str
    version: str
    uses_seed: bool
    defaults: dict[str, Any]


class RunCreate(Schema):
    scenario_version_id: UUID
    algorithm_id: str = Field(min_length=1, max_length=100)
    config: dict[str, Any] = {}
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class RunOut(Schema):
    id: UUID
    scenario_version_id: UUID
    suite_id: UUID | None
    suite_spec: str | None
    repetition: int | None
    algorithm_id: str
    algorithm_version: str
    config: dict[str, Any]
    seed: int | None
    status: str
    attempt: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    cancel_requested_at: datetime | None
    finished_at: datetime | None
    progress: dict[str, Any] | None
    termination_reason: str | None
    error: dict[str, Any] | None


class RunResultOut(Schema):
    run_id: UUID
    feasible: bool
    objective: float | None = Field(description="minutes, shared evaluator")
    total_distance: float | None
    solution: dict[str, Any] | None
    evaluation: dict[str, Any] | None
    iterations: int
    evaluations: int | None
    elapsed_s: float = Field(description="measured wall time")
    time_to_first_feasible_s: float | None
    termination_reason: str
    optimality: str
    seed: int | None
    history: list[Any]
    diagnostics: dict[str, Any]
    created_at: datetime


class CancelResponse(Schema):
    id: UUID
    status: str


# --- suites -----------------------------------------------------------------------------


class SuiteSpecIn(Schema):
    algorithm_id: str = Field(min_length=1, max_length=100)
    config: dict[str, Any] = {}
    label: str | None = Field(default=None, min_length=1, max_length=100)


class SuiteCreate(Schema):
    name: str = Field(min_length=1, max_length=200)
    scenario_version_id: UUID
    specs: list[SuiteSpecIn] = Field(min_length=1, max_length=10)
    seeds: list[Annotated[int, Field(ge=0, le=2**63 - 1)]] | None = Field(
        default=None, min_length=1, max_length=100
    )
    repetitions: int | None = Field(default=None, ge=1, le=100)
    budget_policy: str = Field(default="", max_length=2000)


class SuiteOut(Schema):
    id: UUID
    name: str
    scenario_version_id: UUID
    specs: list[dict[str, Any]]
    seeds: list[int]
    repetitions: int
    budget_policy: str
    created_at: datetime
    status_counts: dict[str, int]
    run_ids: list[UUID]
