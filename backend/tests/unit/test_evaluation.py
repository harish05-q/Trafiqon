import pytest
from helpers import line_scenario

from trafiqon.domain import Solution, VehicleRoute
from trafiqon.routing import build_scenario_matrix, evaluate_solution


def route(vid, customers, start="D", end="D", legs=None):
    return VehicleRoute(vid, tuple(customers), start, end, legs)


def violation_codes(result):
    return sorted(v.code for v in result.violations)


def test_feasible_single_route_objective_is_sum_of_edge_times():
    s = line_scenario()
    r = evaluate_solution(s, Solution((route("v1", ["A", "B"]),)))
    assert r.feasible and r.violations == ()
    # d->a 2, a->b 3, b->a->d 5
    assert r.objective == 10.0
    assert r.total_distance == 10.0
    (rv,) = r.routes
    assert rv.load == 7 and rv.capacity == 10
    assert [leg.edge_ids for leg in rv.legs] == [("d->a",), ("a->b",), ("b->a", "a->d")]


def test_objective_independent_of_matrix_cache():
    s = line_scenario()
    sol = Solution((route("v1", ["B"]), route("v2", ["A"])))
    assert (
        evaluate_solution(s, sol).objective
        == evaluate_solution(s, sol, build_scenario_matrix(s)).objective
        == 14.0
    )  # d->a->b (5) + b->a->d (5) + d->a->d (4)


def test_unused_vehicle_and_empty_route_cost_nothing():
    s = line_scenario()
    r = evaluate_solution(s, Solution((route("v1", ["A", "B"]), route("v2", []))))
    assert r.feasible and r.objective == 10.0


def test_missing_duplicate_unknown_customers():
    s = line_scenario()
    r = evaluate_solution(s, Solution((route("v1", ["A", "A", "Z"]),)))
    assert not r.feasible
    assert violation_codes(r) == ["duplicate_customer", "missing_customer", "unknown_customer"]


def test_capacity_violation_keeps_objective_but_is_infeasible():
    s = line_scenario(capacity=6)
    r = evaluate_solution(s, Solution((route("v1", ["A", "B"]),)))
    assert violation_codes(r) == ["capacity_exceeded"]
    assert not r.feasible
    assert r.objective == 10.0  # pure travel time still reported, flagged infeasible


def test_depot_rules():
    s = line_scenario()
    bad = evaluate_solution(s, Solution((route("v1", ["A", "B"], start="X", end="X"),)))
    assert "unknown_depot" in violation_codes(bad)
    assert "invalid_start_depot" in violation_codes(bad)
    assert "invalid_end_depot" in violation_codes(bad)
    assert bad.objective is None


def test_unknown_and_duplicate_vehicle():
    s = line_scenario()
    r = evaluate_solution(s, Solution((route("v1", ["A"]), route("v1", ["B"]), route("vx", []))))
    assert violation_codes(r) == ["duplicate_vehicle", "unknown_vehicle"]


def test_unreachable_leg_is_infeasible_with_no_objective():
    s = line_scenario()
    g = s.graph.with_edge_closed("a->d")  # b and a can no longer return to depot
    r = evaluate_solution(s.with_graph(g), Solution((route("v1", ["A", "B"]),)))
    assert not r.feasible
    assert r.objective is None
    assert violation_codes(r) == ["unreachable_leg"]


def test_closure_changes_cost_through_detour():
    s = line_scenario()
    g = s.graph.with_edge_closed("a->b")  # d->a->b no longer possible; must use d->b (10)
    r = evaluate_solution(s.with_graph(g), Solution((route("v1", ["B", "A"]),)))
    assert r.feasible
    assert r.objective == 10 + 3 + 2


def test_traffic_change_changes_objective():
    s = line_scenario()
    g = s.graph.with_edge_time("d->a", 20.0)
    r = evaluate_solution(s.with_graph(g), Solution((route("v1", ["A", "B"]),)))
    # d->a now 20, but d->b direct (10) + b->a (3) = 13 is cheaper.
    assert r.routes[0].legs[0].edge_ids == ("d->b", "b->a")
    assert r.objective == 13 + 3 + 5


def test_explicit_legs_are_validated_and_costed_as_given():
    s = line_scenario()
    legs = (("d->b", "b->a"), ("a->b",), ("b->a", "a->d"))
    r = evaluate_solution(s, Solution((route("v1", ["A", "B"], legs=legs),)))
    assert r.feasible
    assert r.objective == 13 + 3 + 5  # not the shortest path, but valid and costed exactly


@pytest.mark.parametrize(
    ("legs", "code"),
    [
        ((("d->a",), ("nope",), ("b->a", "a->d")), "unknown_edge"),
        ((("d->a",), ("a->d", "d->b"), ("b->a", "a->d")), "valid"),
        ((("d->a",), ("b->a",), ("b->a", "a->d")), "discontinuous_leg"),
        ((("d->a",), (), ("b->a", "a->d")), "discontinuous_leg"),
        ((("d->a",), ("a->b",)), "leg_count_mismatch"),
    ],
)
def test_explicit_leg_errors(legs, code):
    s = line_scenario()
    r = evaluate_solution(s, Solution((route("v1", ["A", "B"], legs=legs),)))
    if code == "valid":
        assert r.feasible
        return
    assert violation_codes(r) == [code]
    assert r.objective is None and not r.feasible


def test_explicit_leg_through_closed_edge_rejected():
    s = line_scenario()
    s = s.with_graph(s.graph.with_edge_closed("a->b"))
    legs = (("d->a",), ("a->b",), ("b->a", "a->d"))
    r = evaluate_solution(s, Solution((route("v1", ["A", "B"], legs=legs),)))
    assert violation_codes(r) == ["closed_edge"]
    assert r.objective is None


def test_evaluation_is_pure():
    s = line_scenario()
    sol = Solution((route("v1", ["A", "B"]),))
    edges_before = dict(s.graph.edges)
    assert evaluate_solution(s, sol) == evaluate_solution(s, sol)
    assert dict(s.graph.edges) == edges_before
