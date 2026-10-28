import math
import random

import networkx as nx
import pytest
from helpers import edge, graph, random_graph

from trafiqon.domain import Edge, Graph, Node
from trafiqon.fixtures import BUILTIN_SCENARIOS
from trafiqon.routing import (
    astar,
    dijkstra,
    shortest_path,
    straight_line_heuristic,
    zero_heuristic,
)

ALGORITHMS = ["dijkstra", "astar"]


def _nx_costs(g: Graph, source: str) -> dict[str, float]:
    ng = nx.MultiDiGraph()
    ng.add_nodes_from(g.nodes)
    for e in g.edges.values():
        if e.is_open:
            ng.add_edge(e.source, e.target, weight=e.current_time)
    return nx.single_source_dijkstra_path_length(ng, source, weight="weight")


def _assert_valid_path(g: Graph, path):
    node = path.source
    for eid in path.edge_ids:
        e = g.edges[eid]
        assert e.is_open
        assert e.source == node
        node = e.target
    assert node == path.target
    assert path.node_ids[0] == path.source and path.node_ids[-1] == path.target
    assert len(path.node_ids) == len(path.edge_ids) + 1
    assert path.travel_time == pytest.approx(
        math.fsum(g.edges[e].current_time for e in path.edge_ids)
    )
    assert path.distance == pytest.approx(math.fsum(g.edges[e].distance for e in path.edge_ids))


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_respects_direction(algorithm):
    g = graph("abc", [edge("a", "b", 1), edge("b", "c", 1), edge("c", "a", 1)])
    assert shortest_path(g, "a", "c", algorithm).node_ids == ("a", "b", "c")
    # Reverse direction must go around the cycle, not use a->b backwards.
    assert shortest_path(g, "b", "a", algorithm).node_ids == ("b", "c", "a")


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_closure_forces_detour(algorithm):
    g = graph("abc", [edge("a", "c", 1), edge("a", "b", 2), edge("b", "c", 2)])
    assert shortest_path(g, "a", "c", algorithm).travel_time == 1
    detour = shortest_path(g.with_edge_closed("a->c"), "a", "c", algorithm)
    assert detour.edge_ids == ("a->b", "b->c")
    assert detour.travel_time == 4


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_unreachable_returns_none(algorithm):
    g = graph("abc", [edge("a", "b", 1), edge("c", "b", 1)])
    assert shortest_path(g, "a", "c", algorithm) is None
    closed = graph("ab", [edge("a", "b", 1, closed=True)])
    assert shortest_path(closed, "a", "b", algorithm) is None


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_source_equals_target(algorithm):
    g = graph("ab", [edge("a", "b", 1)])
    p = shortest_path(g, "a", "a", algorithm)
    assert p.edge_ids == () and p.node_ids == ("a",) and p.travel_time == 0


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_unknown_node_raises(algorithm):
    g = graph("ab", [edge("a", "b", 1)])
    with pytest.raises(KeyError):
        shortest_path(g, "a", "zz", algorithm)


def test_picks_cheaper_parallel_edge():
    g = Graph(
        [Node("a"), Node("b")],
        [Edge("slow", "a", "b", 1, 5, 5), Edge("fast", "a", "b", 1, 2, 2)],
    )
    assert shortest_path(g, "a", "b").edge_ids == ("fast",)


def test_dijkstra_matches_networkx_on_random_graphs():
    rng = random.Random(1234)
    for _ in range(200):
        g = random_graph(rng)
        source = rng.choice(list(g.nodes))
        tree = dijkstra(g, source)
        expected = _nx_costs(g, source)
        assert set(tree.time) == set(expected)
        for node, cost in expected.items():
            assert tree.time[node] == pytest.approx(cost)
            _assert_valid_path(g, tree.path_to(node))


@pytest.mark.parametrize("coords", [True, False])
def test_astar_cost_equals_dijkstra_on_random_graphs(coords):
    rng = random.Random(99 if coords else 7)
    for _ in range(200):
        g = random_graph(rng, coords=coords)
        s, t = rng.choice(list(g.nodes)), rng.choice(list(g.nodes))
        d = shortest_path(g, s, t, "dijkstra")
        a = shortest_path(g, s, t, "astar")
        assert (d is None) == (a is None)
        if d is not None:
            assert a.travel_time == pytest.approx(d.travel_time)
            _assert_valid_path(g, a)


@pytest.mark.parametrize("scenario_id", sorted(BUILTIN_SCENARIOS))
def test_astar_equals_dijkstra_on_all_fixture_pairs(scenario_id):
    g = BUILTIN_SCENARIOS[scenario_id]().graph
    for s in g.nodes:
        tree = dijkstra(g, s)
        for t in g.nodes:
            a, _ = astar(g, s, t)
            if t in tree.time:
                assert a.travel_time == pytest.approx(tree.time[t])
            else:
                assert a is None


@pytest.mark.parametrize("scenario_id", sorted(BUILTIN_SCENARIOS))
def test_straight_line_heuristic_is_admissible_and_consistent_on_fixtures(scenario_id):
    g = BUILTIN_SCENARIOS[scenario_id]().graph
    for t in g.nodes:
        h = straight_line_heuristic(g, t)
        assert h is not None
        # True cost to t from every node = Dijkstra on the reversed graph; check via forward trees.
        for s in g.nodes:
            p = shortest_path(g, s, t)
            if p is not None:
                assert h(s) <= p.travel_time + 1e-9
        for e in g.edges.values():
            if e.is_open:
                assert h(e.source) <= e.current_time + h(e.target) + 1e-9


def test_astar_heuristic_reduces_expansions_on_grid():
    g = BUILTIN_SCENARIOS["urban_grid"]().graph
    _, informed = astar(g, "n0_0", "n5_4")
    _, blind = astar(g, "n0_0", "n5_4", heuristic=zero_heuristic)
    assert informed.expanded <= blind.expanded


def test_heuristic_falls_back_when_not_provably_admissible():
    no_coords = graph("ab", [edge("a", "b", 1)])
    assert straight_line_heuristic(no_coords, "b") is None
    zero_time = Graph([Node("a", 0, 0), Node("b", 3, 4)], [edge("a", "b", 0.0, distance=5.0)])
    assert straight_line_heuristic(zero_time, "b") is None
    # A* still correct with the fallback.
    assert shortest_path(zero_time, "a", "b", "astar").travel_time == 0.0


def test_dijkstra_early_stop_only_returns_settled_labels():
    g = graph("abc", [edge("a", "b", 1), edge("a", "c", 5)])
    tree = dijkstra(g, "a", target="b")
    assert tree.time == {"a": 0.0, "b": 1.0}
    assert tree.path_to("c") is None


def test_results_are_deterministic_with_ties():
    g = graph("abcd", [edge("a", "b", 1), edge("a", "c", 1), edge("b", "d", 1), edge("c", "d", 1)])
    paths = {shortest_path(g, "a", "d").edge_ids for _ in range(20)}
    assert len(paths) == 1
