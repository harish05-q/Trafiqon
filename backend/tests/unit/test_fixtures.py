import networkx as nx
import pytest

from trafiqon.domain import Solution, VehicleRoute, validate_scenario
from trafiqon.domain.serialization import scenario_from_dict, scenario_to_dict
from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin
from trafiqon.routing import build_scenario_matrix, check_reachability, evaluate_solution

IDS = sorted(BUILTIN_SCENARIOS)


@pytest.mark.parametrize("scenario_id", IDS)
def test_fixture_is_valid_sized_and_synthetic(scenario_id):
    s = load_builtin(scenario_id)
    assert s.synthetic
    assert validate_scenario(s) == []
    assert 20 <= len(s.graph.nodes) <= 40
    assert 8 <= len(s.customers) <= 15
    assert check_reachability(s) == []


@pytest.mark.parametrize("scenario_id", IDS)
def test_open_network_is_strongly_connected(scenario_id):
    g = load_builtin(scenario_id).graph
    ng = nx.DiGraph()
    ng.add_nodes_from(g.nodes)
    ng.add_edges_from((e.source, e.target) for e in g.edges.values() if e.is_open)
    assert nx.is_strongly_connected(ng)


@pytest.mark.parametrize("scenario_id", IDS)
def test_fixture_is_deterministic_and_round_trips(scenario_id):
    a = scenario_to_dict(load_builtin(scenario_id))
    b = scenario_to_dict(load_builtin(scenario_id))
    assert a == b
    assert scenario_to_dict(scenario_from_dict(a)) == a


def _greedy_split(scenario):
    """Fill vehicles in declaration order; enough to produce a capacity-feasible solution."""
    routes, i = [], 0
    customers = list(scenario.customers)
    for v in scenario.vehicles:
        load, chosen = 0, []
        while i < len(customers) and load + customers[i].demand <= v.capacity:
            load += customers[i].demand
            chosen.append(customers[i].id)
            i += 1
        routes.append(VehicleRoute(v.id, tuple(chosen), v.start_depot_id, v.allowed_end_depots[0]))
    assert i == len(customers)
    return Solution(tuple(routes))


@pytest.mark.parametrize("scenario_id", IDS)
def test_simple_solution_evaluates_feasible(scenario_id):
    s = load_builtin(scenario_id)
    r = evaluate_solution(s, _greedy_split(s), build_scenario_matrix(s))
    assert r.feasible, r.violations
    assert r.objective is not None and r.objective > 0


def test_incident_edges_are_closed_and_avoided():
    s = load_builtin("incident_response")
    closed = {e.id for e in s.graph.edges.values() if e.closed}
    assert closed == set(s.settings["incidents"][0]["edge_ids"])
    m = build_scenario_matrix(s)
    for path in m.paths.values():
        assert not closed & set(path.edge_ids)


def test_congested_core_is_slower_than_base():
    s = load_builtin("congested_city")
    core = [e for e in s.graph.edges.values() if e.congestion == 2.5]
    assert core
    assert all(e.current_time > e.base_time for e in core)


def test_unknown_builtin():
    with pytest.raises(KeyError):
        load_builtin("nope")
