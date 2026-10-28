import random

import networkx as nx
import pytest
from helpers import edge, graph, random_graph

from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin
from trafiqon.optimization import ALGORITHMS, ConfigError
from trafiqon.routing.connectivity import strongly_connected_components


@pytest.mark.parametrize("algorithm_id", sorted(ALGORITHMS))
def test_param_specs_document_exactly_the_config_keys(algorithm_id):
    a = ALGORITHMS[algorithm_id]
    assert [p.key for p in a.params] == list(a.defaults)  # same keys, same order
    for p in a.params:
        assert p.description and p.kind in {"int", "float", "bool", "enum", "enum_list"}
        if p.kind in {"enum", "enum_list"}:
            assert p.choices
        if p.nullable:
            assert p.null_meaning


@pytest.mark.parametrize("algorithm_id", sorted(ALGORITHMS))
def test_param_specs_agree_with_resolve_config(algorithm_id):
    a = ALGORITHMS[algorithm_id]
    a.resolve_config({})
    for p in a.params:
        if p.kind in {"int", "float"}:
            for bound in (p.minimum, p.maximum):
                if bound is not None:
                    a.resolve_config({p.key: int(bound) if p.kind == "int" else bound})
            if p.minimum is not None:
                below = p.minimum - (1 if p.kind == "int" else abs(p.minimum) * 0.5 + 1e-3)
                with pytest.raises(ConfigError):
                    a.resolve_config({p.key: below})
            if p.nullable:
                a.resolve_config({p.key: None})
        elif p.kind == "bool":
            a.resolve_config({p.key: not a.defaults[p.key]})
        elif p.kind == "enum":
            for choice in p.choices:
                a.resolve_config({p.key: choice})
        elif p.kind == "enum_list":
            a.resolve_config({p.key: list(p.choices[:1])})


def _nx_scc(g):
    ng = nx.DiGraph()
    ng.add_nodes_from(g.nodes)
    ng.add_edges_from((e.source, e.target) for e in g.edges.values() if e.is_open)
    return nx.number_strongly_connected_components(ng)


def test_scc_matches_networkx_on_random_graphs():
    rng = random.Random(3)
    for _ in range(200):
        g = random_graph(rng, closed_prob=0.3)
        assert strongly_connected_components(g) == _nx_scc(g)


@pytest.mark.parametrize("scenario_id", sorted(BUILTIN_SCENARIOS))
def test_fixtures_are_one_component(scenario_id):
    assert strongly_connected_components(load_builtin(scenario_id).graph) == 1


def test_scc_respects_closures_and_direction():
    g = graph("abc", [edge("a", "b", 1), edge("b", "a", 1), edge("b", "c", 1)])
    assert strongly_connected_components(g) == 2
    assert strongly_connected_components(g.with_edge_closed("b->a")) == 3


def test_scc_deep_chain_has_no_recursion_limit():
    n = 5000
    nodes = [f"v{i}" for i in range(n)]
    g = graph(
        nodes,
        [edge(nodes[i], nodes[i + 1], 1) for i in range(n - 1)] + [edge(nodes[-1], nodes[0], 1)],
    )
    assert strongly_connected_components(g) == 1
