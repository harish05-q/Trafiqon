"""Domain model: graph, scenario, solution types. No framework dependencies."""

from trafiqon.domain.models import (
    Customer,
    Depot,
    Edge,
    Graph,
    GraphError,
    Node,
    Scenario,
    Vehicle,
)
from trafiqon.domain.solution import Solution, VehicleRoute
from trafiqon.domain.validation import (
    ScenarioValidationError,
    Severity,
    ValidationIssue,
    require_valid,
    validate_scenario,
)

__all__ = [
    "Customer",
    "Depot",
    "Edge",
    "Graph",
    "GraphError",
    "Node",
    "Scenario",
    "ScenarioValidationError",
    "Severity",
    "Solution",
    "ValidationIssue",
    "Vehicle",
    "VehicleRoute",
    "require_valid",
    "validate_scenario",
]
