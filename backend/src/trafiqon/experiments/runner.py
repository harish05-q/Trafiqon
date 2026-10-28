"""Reproducible benchmark runs and summary statistics. See docs/benchmark_methodology.md.

Every number in a report comes from an actual run. Quantity kinds:
  measured - wall-clock timings observed on this machine,
  derived  - computed from stored runs or by the shared evaluator (objective, gap, stats).
"""

from __future__ import annotations

import csv
import io
import math
import platform
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib import metadata
from typing import Any

from trafiqon import __version__
from trafiqon.domain.models import Scenario
from trafiqon.domain.serialization import scenario_fingerprint
from trafiqon.optimization import AlgorithmInput, AlgorithmResult, Optimality, get_algorithm
from trafiqon.optimization.contract import CancelToken, NeverCancel
from trafiqon.routing.cost_matrix import build_scenario_matrix
from trafiqon.routing.evaluation import EVALUATOR_VERSION

QUANTITY_KINDS = {
    "objective": "derived",
    "total_distance": "derived",
    "elapsed_s": "measured",
    "time_to_first_feasible_s": "measured",
    "evaluations": "derived",
    "iterations": "derived",
    "gap_percent": "derived",
}


@dataclass(frozen=True, slots=True)
class RunSpec:
    algorithm_id: str
    config: dict[str, Any] = field(default_factory=dict)
    label: str | None = None

    @property
    def name(self) -> str:
        return self.label or self.algorithm_id


@dataclass(frozen=True, slots=True)
class RunRecord:
    spec: str
    algorithm_id: str
    algorithm_version: str
    seed: int | None
    repetition: int
    config: dict[str, Any]
    feasible: bool
    objective: float | None
    total_distance: float | None
    elapsed_s: float
    time_to_first_feasible_s: float | None
    evaluations: int | None
    iterations: int
    termination_reason: str
    optimality: str


@dataclass(frozen=True, slots=True)
class Summary:
    spec: str
    algorithm_id: str
    n: int
    feasible_count: int
    feasible_rate: float
    objective_mean: float | None
    objective_median: float | None
    objective_std: float | None  # sample std (n-1); None when fewer than 2 feasible runs
    objective_best: float | None
    objective_worst: float | None
    elapsed_mean_s: float
    elapsed_median_s: float
    gap_mean_percent: float | None


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    metadata: dict[str, Any]
    reference: dict[str, Any] | None
    runs: tuple[RunRecord, ...]
    summaries: tuple[Summary, ...]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "reference": self.reference,
            "quantity_kinds": QUANTITY_KINDS,
            "runs": [asdict(r) for r in self.runs],
            "summaries": [asdict(s) for s in self.summaries],
        }

    def runs_csv(self) -> str:
        buf = io.StringIO()
        fields = [f for f in RunRecord.__dataclass_fields__ if f != "config"] + ["config"]
        writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for r in self.runs:
            row = asdict(r)
            row["config"] = repr(sorted(row["config"].items()))
            writer.writerow(row)
        return buf.getvalue()


def software_versions() -> dict[str, str]:
    versions = {"trafiqon": __version__, "python": sys.version.split()[0]}
    for pkg in ("numpy", "ortools"):
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = "not installed"
    versions["platform"] = platform.platform()
    return versions


def run_experiment(
    scenario: Scenario,
    specs: Sequence[RunSpec],
    seeds: Sequence[int],
    *,
    cancel: CancelToken | None = None,
    on_run: Callable[[RunRecord], None] | None = None,
) -> ExperimentReport:
    """Run every spec once per seed on the same scenario and cost matrix.

    Algorithms that take no seed (OR-Tools) are still repeated len(seeds) times; their
    run-to-run variation comes from the time-limited search, and their seed is recorded None.
    """
    started = datetime.now(UTC)
    matrix = build_scenario_matrix(scenario)
    cancel = cancel or NeverCancel()
    runs: list[RunRecord] = []
    for spec in specs:
        algorithm = get_algorithm(spec.algorithm_id)
        config = algorithm.resolve_config(spec.config)
        for rep, seed in enumerate(seeds):
            if cancel.is_cancelled():
                break
            result: AlgorithmResult = algorithm.run(
                AlgorithmInput(scenario, config, seed=seed, cancel=cancel, matrix=matrix)
            )
            record = RunRecord(
                spec=spec.name,
                algorithm_id=result.algorithm_id,
                algorithm_version=result.algorithm_version,
                seed=result.seed,
                repetition=rep,
                config=result.config,
                feasible=result.feasible,
                objective=result.objective,
                total_distance=result.evaluation.total_distance if result.evaluation else None,
                elapsed_s=result.elapsed_s,
                time_to_first_feasible_s=result.time_to_first_feasible_s,
                evaluations=result.evaluations,
                iterations=result.iterations,
                termination_reason=result.termination_reason.value,
                optimality=result.optimality.value,
            )
            runs.append(record)
            if on_run:
                on_run(record)

    reference = reference_value(runs)
    summaries = tuple(summarize(runs, spec.name, reference) for spec in specs)
    return ExperimentReport(
        metadata={
            "created_at": started.isoformat(),
            "scenario_id": scenario.id,
            "scenario_name": scenario.name,
            "scenario_fingerprint": scenario_fingerprint(scenario),
            "synthetic": scenario.synthetic,
            "seeds": list(seeds),
            "specs": [
                {"name": s.name, "algorithm_id": s.algorithm_id, "config": s.config} for s in specs
            ],
            "evaluator_version": EVALUATOR_VERSION,
            "software": software_versions(),
            "cancelled": cancel.is_cancelled(),
        },
        reference=reference,
        runs=tuple(runs),
        summaries=summaries,
    )


def reference_value(runs: Sequence[RunRecord]) -> dict[str, Any] | None:
    """Gap reference: a proven optimum if any run proved one, else the best observed feasible
    objective in this experiment, labelled as a heuristic reference (not an optimum)."""
    feasible = [r for r in runs if r.feasible and r.objective is not None]
    if not feasible:
        return None
    proven = [r for r in feasible if r.optimality == Optimality.PROVEN_OPTIMAL.value]
    pool, kind = (proven, "proven_optimum") if proven else (feasible, "best_observed_heuristic")
    best = min(pool, key=lambda r: r.objective)  # type: ignore[arg-type, return-value]
    return {
        "kind": kind,
        "objective": best.objective,
        "source_spec": best.spec,
        "source_seed": best.seed,
        "source_repetition": best.repetition,
    }


def gap_percent(objective: float, reference: float) -> float:
    """100 * (objective - reference) / reference. Reference must be > 0."""
    if reference <= 0:
        raise ValueError("gap undefined for non-positive reference")
    return 100.0 * (objective - reference) / reference


def summarize(runs: Sequence[RunRecord], spec: str, reference: dict[str, Any] | None) -> Summary:
    mine = [r for r in runs if r.spec == spec]
    objs = [r.objective for r in mine if r.feasible and r.objective is not None]
    times = [r.elapsed_s for r in mine]
    ref = reference["objective"] if reference else None
    gaps = [gap_percent(o, ref) for o in objs] if ref and ref > 0 else []
    return Summary(
        spec=spec,
        algorithm_id=mine[0].algorithm_id if mine else "",
        n=len(mine),
        feasible_count=len(objs),
        feasible_rate=len(objs) / len(mine) if mine else 0.0,
        objective_mean=statistics.fmean(objs) if objs else None,
        objective_median=statistics.median(objs) if objs else None,
        objective_std=statistics.stdev(objs) if len(objs) >= 2 else None,
        objective_best=min(objs) if objs else None,
        objective_worst=max(objs) if objs else None,
        elapsed_mean_s=statistics.fmean(times) if times else math.nan,
        elapsed_median_s=statistics.median(times) if times else math.nan,
        gap_mean_percent=statistics.fmean(gaps) if gaps else None,
    )
