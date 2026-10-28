"""Common contract shared by every optimization algorithm.

Algorithms receive an `AlgorithmInput` and return an `AlgorithmResult`. The objective and
feasibility in every result come from the shared evaluator (`routing.evaluate_solution`)
via `finalize`; an algorithm's internal cost bookkeeping is never reported directly.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from trafiqon.domain.models import Scenario
from trafiqon.domain.solution import Solution
from trafiqon.routing.cost_matrix import CostMatrix, build_scenario_matrix
from trafiqon.routing.evaluation import EvaluationResult, evaluate_solution


class CancelToken(Protocol):
    def is_cancelled(self) -> bool: ...


class CancelFlag:
    """Thread-safe cancellation flag (in-process). The worker supplies a DB-backed token."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class NeverCancel:
    def is_cancelled(self) -> bool:
        return False


class TerminationReason(StrEnum):
    ITERATION_LIMIT = "iteration_limit"
    TIME_LIMIT = "time_limit"
    MIN_TEMPERATURE = "min_temperature"
    NO_IMPROVEMENT = "no_improvement"
    SOLVER_FINISHED = "solver_finished"  # solver stopped on its own criteria
    CANCELLED = "cancelled"
    INFEASIBLE_SCENARIO = "infeasible_scenario"  # proven before search (capacity/reachability)
    NO_SOLUTION_FOUND = "no_solution_found"


class Optimality(StrEnum):
    PROVEN_OPTIMAL = "proven_optimal"
    NOT_PROVEN = "not_proven"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Real execution state only; there is deliberately no percentage field."""

    iteration: int
    evaluations: int | None
    elapsed_s: float
    best_objective: float | None  # best FEASIBLE objective so far (internal estimate)
    current_objective: float | None
    has_feasible: bool
    message: str = ""


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    iteration: int
    evaluations: int | None
    elapsed_s: float
    current_objective: float | None
    best_objective: float | None  # best feasible so far; None until one is found


@dataclass(frozen=True, slots=True)
class AlgorithmInput:
    scenario: Scenario
    config: Mapping[str, Any] = field(default_factory=dict)
    seed: int | None = None
    progress: ProgressCallback | None = None
    cancel: CancelToken = field(default_factory=NeverCancel)
    matrix: CostMatrix | None = None  # cache; must be built from scenario.graph

    def cost_matrix(self) -> CostMatrix:
        return self.matrix or build_scenario_matrix(self.scenario)


@dataclass(frozen=True, slots=True)
class AlgorithmResult:
    algorithm_id: str
    algorithm_version: str
    seed: int | None
    config: dict[str, Any]
    solution: Solution | None  # best feasible solution, if any
    evaluation: EvaluationResult | None  # shared evaluator output for `solution`
    feasible: bool
    objective: float | None  # = evaluation.objective when feasible, else None
    iterations: int
    evaluations: int | None  # None when the solver does not expose a comparable count
    elapsed_s: float
    time_to_first_feasible_s: float | None
    termination_reason: TerminationReason
    optimality: Optimality
    history: tuple[HistoryPoint, ...]
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """Documentation of one configuration key, published so UIs show only real settings.
    `resolve_config` remains the authority; a test checks specs and defaults agree."""

    key: str
    kind: str  # "int" | "float" | "bool" | "enum" | "enum_list"
    description: str
    minimum: float | None = None
    maximum: float | None = None
    nullable: bool = False
    null_meaning: str = ""
    choices: tuple[str, ...] = ()
    unit: str = ""
    advanced: bool = False


class ConfigError(ValueError):
    pass


class Algorithm(Protocol):
    id: str
    version: str
    uses_seed: bool
    defaults: Mapping[str, Any]
    params: tuple[ParamSpec, ...]

    def resolve_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        """Merge with defaults and validate; raise ConfigError on bad input."""
        ...

    def run(self, inp: AlgorithmInput) -> AlgorithmResult: ...


class Stopwatch:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self._t0


def finalize(
    algorithm: Algorithm,
    inp: AlgorithmInput,
    config: dict[str, Any],
    matrix: CostMatrix,
    candidate: Solution | None,
    *,
    seed: int | None,
    iterations: int,
    evaluations: int | None,
    elapsed_s: float,
    time_to_first_feasible_s: float | None,
    termination_reason: TerminationReason,
    optimality: Optimality = Optimality.NOT_PROVEN,
    history: tuple[HistoryPoint, ...] = (),
    diagnostics: dict[str, Any] | None = None,
) -> AlgorithmResult:
    """Score `candidate` with the shared evaluator and build the result.

    If the evaluator rejects the candidate, it is not reported as a solution; the
    violations are kept in diagnostics so the defect is visible rather than hidden.
    """
    diagnostics = dict(diagnostics or {})
    evaluation = evaluate_solution(inp.scenario, candidate, matrix) if candidate else None
    feasible = bool(evaluation and evaluation.feasible)
    if evaluation is not None and not feasible:
        diagnostics["rejected_candidate_violations"] = [
            {"code": v.code, "message": v.message} for v in evaluation.violations
        ]
    return AlgorithmResult(
        algorithm_id=algorithm.id,
        algorithm_version=algorithm.version,
        seed=seed,
        config=config,
        solution=candidate if feasible else None,
        evaluation=evaluation if feasible else None,
        feasible=feasible,
        objective=evaluation.objective if feasible and evaluation else None,
        iterations=iterations,
        evaluations=evaluations,
        elapsed_s=elapsed_s,
        time_to_first_feasible_s=time_to_first_feasible_s if feasible else None,
        termination_reason=termination_reason,
        optimality=optimality if feasible else Optimality.NOT_PROVEN,
        history=history,
        diagnostics=diagnostics,
    )


def check_number(
    cfg: dict[str, Any],
    key: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
    allow_none: bool = False,
) -> None:
    value = cfg[key]
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{key} must be a number")
    if integer and not float(value).is_integer():
        raise ConfigError(f"{key} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{key} must be <= {maximum}")
    if integer:
        cfg[key] = int(value)


def merge_config(
    defaults: Mapping[str, Any], config: Mapping[str, Any], algorithm_id: str
) -> dict[str, Any]:
    unknown = set(config) - set(defaults)
    if unknown:
        raise ConfigError(f"unknown {algorithm_id} config keys: {sorted(unknown)}")
    return {**defaults, **config}
