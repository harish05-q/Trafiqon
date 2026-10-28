from dataclasses import replace

import pytest
from helpers import line_scenario

from trafiqon.domain import (
    Customer,
    Depot,
    ScenarioValidationError,
    Severity,
    Vehicle,
    require_valid,
    validate_scenario,
)


def codes(scenario):
    return sorted(i.code for i in validate_scenario(scenario))


def test_valid_scenario_has_no_issues():
    assert validate_scenario(line_scenario()) == []


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"depots": ()}, "no_depots"),
        ({"vehicles": ()}, "no_vehicles"),
        ({"depots": (Depot("D", "zz"),)}, "unknown_node"),
        ({"customers": (Customer("A", "a", 1), Customer("A", "b", 1))}, "duplicate_customer"),
        ({"customers": (Customer("A", "zz", 1),)}, "unknown_node"),
        ({"customers": (Customer("A", "d", 1),)}, "customer_at_depot"),
        ({"customers": (Customer("A", "a", 0),)}, "invalid_demand"),
        ({"vehicles": (Vehicle("v", 0, "D"), Vehicle("w", 9, "D"))}, "invalid_capacity"),
        ({"vehicles": (Vehicle("v", 9, "X"),)}, "unknown_depot"),
        ({"vehicles": (Vehicle("v", 9, "D", ("X",)),)}, "unknown_depot"),
        ({"vehicles": (Vehicle("v", 9, "D"), Vehicle("v", 9, "D"))}, "duplicate_vehicle"),
    ],
)
def test_structural_errors(change, code):
    scenario = replace(line_scenario(), **change)
    assert code in codes(scenario)
    with pytest.raises(ScenarioValidationError):
        require_valid(scenario)


def test_capacity_infeasibility_is_reported_but_not_rejected():
    big_demand = line_scenario(capacity=5, demands=(6, 1))
    issues = validate_scenario(big_demand)
    assert [(i.code, i.severity) for i in issues] == [
        ("demand_exceeds_capacity", Severity.INFEASIBLE)
    ]
    assert require_valid(big_demand) is big_demand

    too_much = replace(line_scenario(capacity=4, demands=(4, 4)), vehicles=(Vehicle("v1", 4, "D"),))
    assert codes(too_much) == ["insufficient_fleet_capacity"]
