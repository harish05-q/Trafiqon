"""Benchmark suites: a suite is a set of ordinary runs (specs x seeds) on one scenario
version. Comparison and export are computed from STORED run results only."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trafiqon.api import deps
from trafiqon.api.errors import ApiError
from trafiqon.api.routers.runs import prepare
from trafiqon.api.schemas import ErrorResponse, Page, SuiteCreate, SuiteOut
from trafiqon.experiments.runner import (
    ExperimentReport,
    RunRecord,
    reference_value,
    summarize,
)
from trafiqon.persistence import runs as run_repo
from trafiqon.persistence.models import BenchmarkSuiteRow, RunResultRow, RunRow, RunStatus
from trafiqon.persistence.scenarios import get_version
from trafiqon.routing.evaluation import EVALUATOR_VERSION
from trafiqon.settings import Settings
from trafiqon.worker.queue import JobQueue

router = APIRouter(prefix="/api/v1/suites", tags=["experiments"])
ERRORS = {
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


def _load(session: Session, suite_id: uuid.UUID) -> BenchmarkSuiteRow:
    row = session.get(BenchmarkSuiteRow, suite_id)
    if row is None:
        raise ApiError(404, "suite_not_found", f"suite {suite_id} not found")
    return row


def _runs(session: Session, suite_id: uuid.UUID) -> list[RunRow]:
    return list(
        session.scalars(
            select(RunRow)
            .where(RunRow.suite_id == suite_id)
            .order_by(RunRow.suite_spec, RunRow.repetition)
        ).all()
    )


def _out(session: Session, row: BenchmarkSuiteRow) -> SuiteOut:
    runs = _runs(session, row.id)
    return SuiteOut(
        id=row.id,
        name=row.name,
        scenario_version_id=row.scenario_version_id,
        specs=row.specs,
        seeds=row.seeds,
        repetitions=row.repetitions,
        budget_policy=row.budget_policy,
        created_at=row.created_at,
        status_counts=dict(Counter(r.status for r in runs)),
        run_ids=[r.id for r in runs],
    )


@router.post("", status_code=202, response_model=SuiteOut, responses=ERRORS)
def launch_suite(
    body: SuiteCreate,
    response: Response,
    session: Session = Depends(deps.db),
    queue: JobQueue = Depends(deps.queue),
    settings: Settings = Depends(deps.settings),
) -> SuiteOut:
    """Create the suite and all of its runs in one transaction. Seeds: `seeds`, or
    0..repetitions-1. Algorithms that take no seed are simply repeated."""
    if get_version(session, body.scenario_version_id) is None:
        raise ApiError(
            404, "version_not_found", f"scenario version {body.scenario_version_id} not found"
        )
    if body.seeds is None and body.repetitions is None:
        raise ApiError(422, "invalid_request", "provide `seeds` or `repetitions`")
    seeds = body.seeds if body.seeds is not None else list(range(body.repetitions or 0))
    if body.repetitions is not None and body.seeds is not None and body.repetitions != len(seeds):
        raise ApiError(422, "invalid_request", "`repetitions` must equal len(`seeds`)")
    labels = [s.label or s.algorithm_id for s in body.specs]
    if len(set(labels)) != len(labels):
        raise ApiError(
            422, "duplicate_spec_label", "give specs with the same algorithm distinct labels"
        )
    total = len(body.specs) * len(seeds)
    if total > settings.limits.max_suite_runs:
        raise ApiError(
            422, "suite_too_large", f"{total} runs exceeds limit {settings.limits.max_suite_runs}"
        )
    if run_repo.count_queued(session) + total > settings.limits.max_queued_runs:
        raise ApiError(429, "queue_full", "too many queued runs; retry later")

    prepared = []
    for spec, label in zip(body.specs, labels, strict=True):
        algorithm, config, _ = prepare(spec.algorithm_id, spec.config, 0, settings.limits)
        prepared.append((label, algorithm, config))
    suite = BenchmarkSuiteRow(
        name=body.name,
        scenario_version_id=body.scenario_version_id,
        specs=[
            {"label": lb, "algorithm_id": a.id, "algorithm_version": a.version, "config": c}
            for lb, a, c in prepared
        ],
        seeds=seeds,
        repetitions=len(seeds),
        budget_policy=body.budget_policy,
    )
    session.add(suite)
    session.flush()
    for label, algorithm, config in prepared:
        for rep, seed in enumerate(seeds):
            run = run_repo.new_run(
                scenario_version_id=body.scenario_version_id,
                algorithm_id=algorithm.id,
                algorithm_version=algorithm.version,
                config=config,
                seed=seed if algorithm.uses_seed else None,
                max_attempts=settings.max_attempts,
                suite_id=suite.id,
                suite_spec=label,
                repetition=rep,
            )
            queue.enqueue(session, run)
    session.commit()
    response.headers["Location"] = f"/api/v1/suites/{suite.id}"
    return _out(session, suite)


@router.get("", response_model=Page[SuiteOut])
def list_suites(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(deps.db),
) -> Page[SuiteOut]:
    total = session.scalar(select(func.count()).select_from(BenchmarkSuiteRow)) or 0
    rows = session.scalars(
        select(BenchmarkSuiteRow)
        .order_by(BenchmarkSuiteRow.created_at.desc(), BenchmarkSuiteRow.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[SuiteOut](
        items=[_out(session, r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{suite_id}", response_model=SuiteOut, responses=ERRORS)
def get_suite(suite_id: uuid.UUID, session: Session = Depends(deps.db)) -> SuiteOut:
    return _out(session, _load(session, suite_id))


def build_report(session: Session, suite: BenchmarkSuiteRow) -> tuple[ExperimentReport, dict]:
    """Experiment report from stored results. Only COMPLETED runs enter the statistics;
    cancelled, failed and unfinished runs are counted separately, never imputed."""
    runs = _runs(session, suite.id)
    results = {
        r.run_id: r
        for r in session.scalars(
            select(RunResultRow).where(RunResultRow.run_id.in_([r.id for r in runs]))
        ).all()
    }
    records = []
    for run in runs:
        res = results.get(run.id)
        if run.status != RunStatus.COMPLETED or res is None:
            continue
        records.append(
            RunRecord(
                spec=run.suite_spec or run.algorithm_id,
                algorithm_id=run.algorithm_id,
                algorithm_version=run.algorithm_version,
                seed=res.seed,
                repetition=run.repetition or 0,
                config=run.config,
                feasible=res.feasible,
                objective=res.objective,
                total_distance=res.total_distance,
                elapsed_s=res.elapsed_s,
                time_to_first_feasible_s=res.time_to_first_feasible_s,
                evaluations=res.evaluations,
                iterations=res.iterations,
                termination_reason=res.termination_reason,
                optimality=res.optimality,
            )
        )
    reference = reference_value(records)
    labels = [s["label"] for s in suite.specs]
    counts = {lb: dict(Counter(r.status for r in runs if r.suite_spec == lb)) for lb in labels}
    version = get_version(session, suite.scenario_version_id)
    software = sorted(
        {tuple(sorted(res.diagnostics.get("software", {}).items())) for res in results.values()}
    )
    report = ExperimentReport(
        metadata={
            "suite_id": str(suite.id),
            "suite_name": suite.name,
            "created_at": suite.created_at.isoformat(),
            "scenario_version_id": str(suite.scenario_version_id),
            "scenario_fingerprint": version.fingerprint if version else None,
            "synthetic": version.synthetic if version else None,
            "seeds": suite.seeds,
            "specs": suite.specs,
            "budget_policy": suite.budget_policy,
            "evaluator_version": EVALUATOR_VERSION,
            "software": [dict(s) for s in software],
            "statistics_include": "COMPLETED runs only",
        },
        reference=reference,
        runs=tuple(records),
        summaries=tuple(summarize(records, lb, reference) for lb in labels),
    )
    return report, counts


@router.get("/{suite_id}/comparison", responses=ERRORS)
def comparison(suite_id: uuid.UUID, session: Session = Depends(deps.db)) -> dict[str, Any]:
    suite = _load(session, suite_id)
    report, counts = build_report(session, suite)
    total = sum(sum(c.values()) for c in counts.values())
    finished = sum(
        n
        for c in counts.values()
        for st, n in c.items()
        if st in ("COMPLETED", "CANCELLED", "FAILED")
    )
    data = report.to_json_dict()
    data.pop("runs")
    return {**data, "status_counts_by_spec": counts, "complete": finished == total}


@router.get("/{suite_id}/export", responses=ERRORS)
def export(
    suite_id: uuid.UUID,
    format: str = Query("json", pattern="^(json|csv)$"),
    session: Session = Depends(deps.db),
    settings: Settings = Depends(deps.settings),
) -> Response:
    suite = _load(session, suite_id)
    report, counts = build_report(session, suite)
    if len(report.runs) > settings.limits.max_export_runs:
        raise ApiError(422, "export_too_large", "suite exceeds the export size limit")
    name = f"suite-{suite.id}"
    if format == "csv":
        return Response(
            report.runs_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    body = json.dumps({**report.to_json_dict(), "status_counts_by_spec": counts}, indent=2)
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}.json"'},
    )
