import pytest
from helpers import edge, graph

from trafiqon.domain import Edge, Graph, GraphError, Node


def test_edges_are_directed():
    g = graph("ab", [edge("a", "b", 1.0)])
    assert [e.target for e in g.out_edges("a")] == ["b"]
    assert g.out_edges("b") == ()
    assert [e.source for e in g.in_edges("b")] == ["a"]


def test_closed_edges_hidden_unless_requested():
    g = graph("ab", [edge("a", "b", 1.0, closed=True)])
    assert g.out_edges("a") == ()
    assert len(g.out_edges("a", include_closed=True)) == 1


def test_parallel_edges_allowed_and_ordered_by_id():
    g = Graph(
        [Node("a"), Node("b")],
        [Edge("z", "a", "b", 1, 1, 1), Edge("m", "a", "b", 1, 2, 2)],
    )
    assert [e.id for e in g.out_edges("a")] == ["m", "z"]


@pytest.mark.parametrize(
    ("nodes", "edges", "match"),
    [
        ([Node("a"), Node("a")], [], "duplicate node"),
        ([Node("a"), Node("b")], [Edge("e", "a", "x", 1, 1, 1)], "target"),
        ([Node("a"), Node("b")], [Edge("e", "x", "b", 1, 1, 1)], "source"),
        ([Node("a")], [Edge("e", "a", "a", 1, 1, 1)], "self-loop"),
        ([Node("a"), Node("b")], [Edge("e", "a", "b", 1, 1, -1)], "current_time"),
        ([Node("a"), Node("b")], [Edge("e", "a", "b", float("nan"), 1, 1)], "distance"),
        ([Node("a"), Node("b")], [Edge("e", "a", "b", 1, float("inf"), 1)], "base_time"),
        (
            [Node("a"), Node("b")],
            [Edge("e", "a", "b", 1, 1, 1), Edge("e", "b", "a", 1, 1, 1)],
            "duplicate edge",
        ),
    ],
)
def test_invalid_graphs_rejected(nodes, edges, match):
    with pytest.raises(GraphError, match=match):
        Graph(nodes, edges)


def test_updates_return_new_graph_and_keep_original():
    g = graph("ab", [edge("a", "b", 1.0)])
    closed = g.with_edge_closed("a->b")
    slower = g.with_edge_time("a->b", 7.5)
    assert g.edges["a->b"].is_open
    assert closed.edges["a->b"].closed
    assert slower.edges["a->b"].current_time == 7.5
    assert g.edges["a->b"].current_time == 1.0
    with pytest.raises(GraphError, match="unknown edge"):
        g.with_edges([edge("b", "a", 1.0)])
