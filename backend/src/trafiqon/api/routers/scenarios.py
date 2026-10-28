"""Persisted scenarios and immutable versions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from trafiqon.api import deps
from trafiqon.api.errors import ApiError
from trafiqon.api.schemas import (
    ErrorResponse,
    Page,
    ScenarioCreate,
    ScenarioData,
    ScenarioDetail,
    ScenarioOut,
    ScenarioRecord,
    ScenarioUpdate,
    ScenarioValidation,
    ValidationIssueOut,
    VersionCreate,
    VersionOut,
    VersionSummary,
)
from trafiqon.domain.models import GraphError, Scenario
from trafiqon.domain.serialization import scenario_from_dict
from trafiqon.domain.validation import Severity, validate_scenario
from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin
from trafiqon.persistence import scenarios as repo
from trafiqon.persistence.models import ScenarioRow, ScenarioVersionRow
from trafiqon.routing import build_scenario_matrix, check_reachability
from trafiqon.routing.connectivity import strongly_connected_components
from trafiqon.settings import Settings

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])
ERRORS = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def build_scenario(data: ScenarioData, name: str, settings: Settings) -> Scenario:
    """Validate submitted content into a domain Scenario (structure, limits, references)."""
    lim = settings.limits
    counts = {
        "nodes": (len(data.graph.nodes), lim.max_nodes),
        "edges": (len(data.graph.edges), lim.max_edges),
        "customers": (len(data.customers), lim.max_customers),
        "vehicles": (len(data.vehicles), lim.max_vehicles),
    }
    too_big = {k: {"count": c, "limit": m} for k, (c, m) in counts.items() if c > m}
    if too_big:
        raise ApiError(422, "scenario_too_large", "scenario exceeds configured limits", too_big)
    raw = data.model_dump()
    raw.update(id="pending", name=name)
    try:
        scenario = scenario_from_dict(raw)
    except (GraphError, KeyError, ValueError) as exc:
        raise ApiError(422, "invalid_graph", str(exc)) from None
    errors = [i for i in validate_scenario(scenario) if i.severity is Severity.ERROR]
    if errors:
        raise ApiError(
            422,
            "invalid_scenario",
            "scenario failed validation",
            [{"code": i.code, "message": i.message, "ref": i.ref} for i in errors],
        )
    return scenario


def _load(session: Session, scenario_id: uuid.UUID) -> ScenarioRow:
    row = repo.get_scenario(session, scenario_id)
    if row is None:
        raise ApiError(404, "scenario_not_found", f"scenario {scenario_id} not found")
    return row


def _detail(session: Session, row: ScenarioRow) -> ScenarioDetail:
    return ScenarioDetail(
        **ScenarioRecord.model_validate(row, from_attributes=True).model_dump(),
        versions=[
            VersionSummary.model_validate(v, from_attributes=True)
            for v in repo.list_versions(session, row.id)
        ],
    )


def version_out(v: ScenarioVersionRow) -> VersionOut:
    return VersionOut(
        **VersionSummary.model_validate(v, from_attributes=True).model_dump(),
        data=ScenarioOut.model_validate(v.data),
    )


@router.get("", response_model=Page[ScenarioRecord])
def list_scenarios(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(deps.db),
) -> Page[ScenarioRecord]:
    rows, total = repo.list_scenarios(session, limit, offset)
    items = [ScenarioRecord.model_validate(r, from_attributes=True) for r in rows]
    return Page[ScenarioRecord](items=items, total=total, limit=limit, offset=offset)


@router.post("", status_code=201, response_model=ScenarioDetail, responses=ERRORS)
def create_scenario(
    body: ScenarioCreate,
    response: Response,
    session: Session = Depends(deps.db),
    settings: Settings = Depends(deps.settings),
) -> ScenarioDetail:
    """Create a scenario with version 1, from `data` or by copying `builtin_id`."""
    if (body.data is None) == (body.builtin_id is None):
        raise ApiError(422, "invalid_request", "provide exactly one of `data` or `builtin_id`")
    if body.builtin_id is not None:
        if body.builtin_id not in BUILTIN_SCENARIOS:
            raise ApiError(404, "scenario_not_found", f"unknown built-in {body.builtin_id!r}")
        scenario = load_builtin(body.builtin_id)
        note = f"copied from built-in {body.builtin_id}"
    else:
        scenario = build_scenario(body.data, body.name, settings)  # type: ignore[arg-type]
        note = ""
    row = repo.create_scenario(session, body.name, body.description)
    repo.add_version(session, row, scenario, note=note)
    session.commit()
    response.headers["Location"] = f"/api/v1/scenarios/{row.id}"
    return _detail(session, row)


@router.post("/validate", response_model=ScenarioValidation, responses=ERRORS)
def validate(body: ScenarioData, settings: Settings = Depends(deps.settings)) -> ScenarioValidation:
    """Check content without saving: structure, capacity, reachability and connectivity.
    `feasible_so_far` means no infeasibility was DETECTED; it does not prove a solution
    exists (bin-packing can still fail)."""
    issues: list[ValidationIssueOut] = []
    lim = settings.limits
    for kind, count, maximum in (
        ("nodes", len(body.graph.nodes), lim.max_nodes),
        ("edges", len(body.graph.edges), lim.max_edges),
        ("customers", len(body.customers), lim.max_customers),
        ("vehicles", len(body.vehicles), lim.max_vehicles),
    ):
        if count > maximum:
            issues.append(
                ValidationIssueOut(
                    code="scenario_too_large",
                    severity="error",
                    message=f"{count} {kind} exceeds limit {maximum}",
                )
            )
    raw = body.model_dump()
    raw.update(id="draft", name="draft")
    try:
        scenario = scenario_from_dict(raw)
    except (GraphError, KeyError, ValueError) as exc:
        issues.append(ValidationIssueOut(code="invalid_graph", severity="error", message=str(exc)))
        return ScenarioValidation(
            valid=False,
            feasible_so_far=False,
            issues=issues,
            strongly_connected_components=None,
            unreachable_location_pairs=None,
            total_demand=None,
            total_capacity=None,
        )
    for i in validate_scenario(scenario):
        issues.append(
            ValidationIssueOut(code=i.code, message=i.message, ref=i.ref, severity=i.severity.value)
        )
    valid = not any(i.severity == "error" for i in issues)
    unreachable_pairs = None
    if valid:
        matrix = build_scenario_matrix(scenario)
        unreachable_pairs = len(matrix.unreachable_pairs())
        for r in check_reachability(scenario, matrix):
            issues.append(
                ValidationIssueOut(code=r.code, message=r.message, ref=r.ref, severity="infeasible")
            )
    components = strongly_connected_components(scenario.graph)
    if components > 1:
        issues.append(
            ValidationIssueOut(
                code="not_strongly_connected",
                severity="warning",
                message=f"open roads form {components} strongly connected components",
            )
        )
    return ScenarioValidation(
        valid=valid,
        feasible_so_far=valid and not any(i.severity == "infeasible" for i in issues),
        issues=issues,
        strongly_connected_components=components,
        unreachable_location_pairs=unreachable_pairs,
        total_demand=sum(c.demand for c in scenario.customers),
        total_capacity=sum(v.capacity for v in scenario.vehicles),
    )


@router.get("/{scenario_id}", response_model=ScenarioDetail, responses=ERRORS)
def get_scenario(scenario_id: uuid.UUID, session: Session = Depends(deps.db)) -> ScenarioDetail:
    return _detail(session, _load(session, scenario_id))


@router.patch("/{scenario_id}", response_model=ScenarioDetail, responses=ERRORS)
def update_scenario(
    scenario_id: uuid.UUID, body: ScenarioUpdate, session: Session = Depends(deps.db)
) -> ScenarioDetail:
    """Metadata only. Graph, demand or fleet changes require a new version."""
    row = repo.update_metadata(session, _load(session, scenario_id), body.model_dump())
    session.commit()
    return _detail(session, row)


@router.delete("/{scenario_id}", status_code=204, responses=ERRORS)
def delete_scenario(scenario_id: uuid.UUID, session: Session = Depends(deps.db)) -> Response:
    row = _load(session, scenario_id)
    try:
        repo.delete_scenario(session, row)
    except repo.ScenarioInUse:
        raise ApiError(
            409,
            "scenario_in_use",
            "a version of this scenario is referenced by runs or benchmark suites",
        ) from None
    session.commit()
    return Response(status_code=204)


@router.post(
    "/{scenario_id}/versions", status_code=201, response_model=VersionOut, responses=ERRORS
)
def create_version(
    scenario_id: uuid.UUID,
    body: VersionCreate,
    session: Session = Depends(deps.db),
    settings: Settings = Depends(deps.settings),
) -> VersionOut:
    row = _load(session, scenario_id)
    version = repo.add_version(
        session, row, build_scenario(body.data, row.name, settings), body.note
    )
    session.commit()
    return version_out(version)


@router.get("/{scenario_id}/versions/{number}", response_model=VersionOut, responses=ERRORS)
def get_version(
    scenario_id: uuid.UUID, number: int, session: Session = Depends(deps.db)
) -> VersionOut:
    version = repo.get_version_by_number(session, scenario_id, number)
    if version is None:
        raise ApiError(404, "version_not_found", f"version {number} of {scenario_id} not found")
    return version_out(version)


versions_router = APIRouter(prefix="/api/v1/scenario-versions", tags=["scenarios"])


@versions_router.get("/{version_id}", response_model=VersionOut, responses=ERRORS)
def get_version_by_id(version_id: uuid.UUID, session: Session = Depends(deps.db)) -> VersionOut:
    version = repo.get_version(session, version_id)
    if version is None:
        raise ApiError(404, "version_not_found", f"scenario version {version_id} not found")
    return version_out(version)
