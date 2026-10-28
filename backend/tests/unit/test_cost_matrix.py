import math

import numpy as np
from helpers import edge, graph, line_scenario

from trafiqon.domain import Customer, Depot, Scenario, Vehicle
from trafiqon.routing import build_cost_matrix, build_scenario_matrix, check_reachability


def test_matrix_is_directed_and_keeps_leg_paths():
    m = build_scenario_matrix(line_scenario())
    assert m.node_ids == ("d", "a", "b")
    i, j = m.index["d"], m.index["b"]
    # d->b: via a (2+3=5) beats the direct one-way edge (10).
    assert m.time[i, j] == 5.0
    assert m.leg("d", "b").edge_ids == ("d->a", "a->b")
    # b->d has no direct edge: must go back via a.
    assert m.leg("b", "d").edge_ids == ("b->a", "a->d")
    assert np.all(np.diag(m.time) == 0)
    assert m.reachable.all()
    assert m.unreachable_pairs() == []


def test_unreachable_pairs_are_explicit_not_big_m():
    g = graph("abc", [edge("a", "b", 1), edge("b", "a", 1), edge("a", "c", 1)])
    m = build_cost_matrix(g, ["a", "b", "c"])
    k = m.index
    assert not m.reachable[k["c"], k["a"]]
    assert math.isnan(m.time[k["c"], k["a"]])
    assert math.isnan(m.distance[k["c"], k["a"]])
    assert m.leg("c", "a") is None
    assert set(m.unreachable_pairs()) == {("c", "a"), ("c", "b")}


def test_matrix_dedupes_locations():
    g = graph("ab", [edge("a", "b", 1)])
    m = build_cost_matrix(g, ["a", "b", "a"])
    assert m.node_ids == ("a", "b")
    assert m.time.shape == (2, 2)


def test_check_reachability_flags_customer_without_return_path():
    g = graph("dxy", [edge("d", "x", 1), edge("x", "d", 1), edge("d", "y", 1)])
    s = Scenario(
        id="s",
        name="s",
        graph=g,
        depots=(Depot("D", "d"),),
        customers=(Customer("X", "x", 1), Customer("Y", "y", 1)),
        vehicles=(Vehicle("v", 5, "D"),),
    )
    issues = check_reachability(s)
    assert [i.ref for i in issues] == ["Y"]


def test_check_reachability_respects_end_depots_and_capacity():
    # y can only return to depot E; only v2 may end there, but v2 is too small for Y.
    g = graph("dey", [edge("d", "y", 1), edge("y", "e", 1)])
    base = dict(
        id="s",
        name="s",
        graph=g,
        depots=(Depot("D", "d"), Depot("E", "e")),
        customers=(Customer("Y", "y", 4),),
    )
    small = Scenario(**base, vehicles=(Vehicle("v1", 9, "D"), Vehicle("v2", 3, "D", ("E",))))
    assert [i.ref for i in check_reachability(small)] == ["Y"]
    ok = Scenario(**base, vehicles=(Vehicle("v2", 4, "D", ("E",)),))
    assert check_reachability(ok) == []
