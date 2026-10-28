"""Optimization algorithms behind one common contract (see contract.py)."""

from trafiqon.optimization.contract import (
    Algorithm,
    AlgorithmInput,
    AlgorithmResult,
    CancelFlag,
    ConfigError,
    HistoryPoint,
    Optimality,
    ProgressEvent,
    TerminationReason,
)
from trafiqon.optimization.ortools_cvrp import OrToolsCvrp
from trafiqon.optimization.simulated_annealing import SimulatedAnnealing

ALGORITHMS: dict[str, Algorithm] = {a.id: a for a in (OrToolsCvrp(), SimulatedAnnealing())}


def get_algorithm(algorithm_id: str) -> Algorithm:
    try:
        return ALGORITHMS[algorithm_id]
    except KeyError:
        raise ConfigError(f"unknown algorithm {algorithm_id!r}") from None


__all__ = [
    "ALGORITHMS",
    "Algorithm",
    "AlgorithmInput",
    "AlgorithmResult",
    "CancelFlag",
    "ConfigError",
    "HistoryPoint",
    "Optimality",
    "OrToolsCvrp",
    "ProgressEvent",
    "SimulatedAnnealing",
    "TerminationReason",
    "get_algorithm",
]
