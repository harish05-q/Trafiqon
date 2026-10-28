"""Structural scenario validation (no shortest paths; reachability lives in routing)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from trafiqon.domain.models import Scenario


class Severity(StrEnum):
    ERROR = "error"  # scenario is malformed and must be rejected
    INFEASIBLE = "infeasible"  # well-formed, but no valid solution can exist


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: Severity = Severity.ERROR
    ref: str | None = None


class ScenarioValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in issues))


def validate_scenario(scenario: Scenario) -> list[ValidationIssue]:
    """Return every structural and capacity issue. An empty list means well-formed and
    not trivially infeasible; reachability must still be checked with `routing`."""
    issues: list[ValidationIssue] = []
    graph = scenario.graph

    for kind, items in (
        ("depot", scenario.depots),
        ("customer", scenario.customers),
        ("vehicle", scenario.vehicles),
    ):
        for item_id, count in Counter(i.id for i in items).items():
            if count > 1:
                issues.append(
                    ValidationIssue(
                        f"duplicate_{kind}", f"{kind} id {item_id!r} repeated", ref=item_id
                    )
                )

    if not scenario.depots:
        issues.append(ValidationIssue("no_depots", "scenario has no depots"))
    if not scenario.vehicles:
        issues.append(ValidationIssue("no_vehicles", "scenario has no vehicles"))

    for depot in scenario.depots:
        if not graph.has_node(depot.node_id):
            issues.append(
                ValidationIssue(
                    "unknown_node",
                    f"depot {depot.id!r} node {depot.node_id!r} missing",
                    ref=depot.id,
                )
            )

    depot_ids = {d.id for d in scenario.depots}
    depot_nodes = {d.node_id for d in scenario.depots}
    for customer in scenario.customers:
        if not graph.has_node(customer.node_id):
            issues.append(
                ValidationIssue(
                    "unknown_node",
                    f"customer {customer.id!r} node {customer.node_id!r} missing",
                    ref=customer.id,
                )
            )
        if customer.node_id in depot_nodes:
            issues.append(
                ValidationIssue(
                    "customer_at_depot",
                    f"customer {customer.id!r} is located at a depot node",
                    ref=customer.id,
                )
            )
        if customer.demand <= 0:
            issues.append(
                ValidationIssue(
                    "invalid_demand",
                    f"customer {customer.id!r} demand must be > 0",
                    ref=customer.id,
                )
            )

    for vehicle in scenario.vehicles:
        if vehicle.capacity <= 0:
            issues.append(
                ValidationIssue(
                    "invalid_capacity",
                    f"vehicle {vehicle.id!r} capacity must be > 0",
                    ref=vehicle.id,
                )
            )
        for depot_id in (vehicle.start_depot_id, *vehicle.end_depot_ids):
            if depot_id not in depot_ids:
                issues.append(
                    ValidationIssue(
                        "unknown_depot",
                        f"vehicle {vehicle.id!r} references unknown depot {depot_id!r}",
                        ref=vehicle.id,
                    )
                )

    capacities = [v.capacity for v in scenario.vehicles if v.capacity > 0]
    max_capacity = max(capacities, default=0)
    for customer in scenario.customers:
        if customer.demand > max_capacity:
            issues.append(
                ValidationIssue(
                    "demand_exceeds_capacity",
                    f"customer {customer.id!r} demand {customer.demand} exceeds the largest "
                    f"vehicle capacity {max_capacity}",
                    Severity.INFEASIBLE,
                    ref=customer.id,
                )
            )
    total_demand = sum(c.demand for c in scenario.customers if c.demand > 0)
    if total_demand > sum(capacities):
        issues.append(
            ValidationIssue(
                "insufficient_fleet_capacity",
                f"total demand {total_demand} exceeds total fleet capacity {sum(capacities)}",
                Severity.INFEASIBLE,
            )
        )
    return issues


def require_valid(scenario: Scenario) -> Scenario:
    """Raise if the scenario has structural errors; infeasibility issues are allowed."""
    errors = [i for i in validate_scenario(scenario) if i.severity is Severity.ERROR]
    if errors:
        raise ScenarioValidationError(errors)
    return scenario
