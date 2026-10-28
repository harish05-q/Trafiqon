"""Small builders shared by tests."""

from __future__ import annotations

import math
import random

from trafiqon.domain import Customer, Depot, Edge, Graph, Node, Scenario, Vehicle


def edge(
    u: str, v: str, time: float, *, distance: float | None = None, closed: bool = False
) -> Edge:
    return Edge(
        id=f"{u}->{v}",
        source=u,
        target=v,
        distance=time if distance is None else distance,
        base_time=time,
        current_time=time,
        closed=closed,
    )


def graph(node_ids: str | list[str], edges: list[Edge]) -> Graph:
    ids = list(node_ids)
    return Graph([Node(n) for n in ids], edges)


def random_graph(rng: random.Random, *, coords: bool = True, closed_prob: float = 0.1) -> Graph:
    """Random directed graph. Edge time >= straight-line length / 1.0 so the straight-line
    heuristic is meaningful, plus some zero-length/closed edges."""
    n = rng.randint(2, 25)
    nodes = [
        Node(f"v{i}", x=rng.uniform(0, 10), y=rng.uniform(0, 10)) if coords else Node(f"v{i}")
        for i in range(n)
    ]
    edges: list[Edge] = []
    for _ in range(rng.randint(0, n * 4)):
        a, b = rng.sample(nodes, 2)
        eid = f"e{len(edges)}"
        length = math.hypot(a.x - b.x, a.y - b.y) if coords else rng.uniform(0, 10)
        t = round(length * rng.uniform(1.0, 3.0), 4)
        edges.append(Edge(eid, a.id, b.id, length, t, t, closed=rng.random() < closed_prob))
    return Graph(nodes, edges)


def line_scenario(*, capacity: int = 10, demands: tuple[int, ...] = (3, 4)) -> Scenario:
    """Depot D on node d; customers on nodes a, b; two-way roads d<->a<->b, plus d->b direct.

    d --2-- a --3-- b      plus one-way d->b (10)
    """
    g = graph(
        ["d", "a", "b"],
        [
            edge("d", "a", 2.0),
            edge("a", "d", 2.0),
            edge("a", "b", 3.0),
            edge("b", "a", 3.0),
            edge("d", "b", 10.0),
        ],
    )
    return Scenario(
        id="line",
        name="line",
        graph=g,
        depots=(Depot("D", "d"),),
        customers=(Customer("A", "a", demands[0]), Customer("B", "b", demands[1])),
        vehicles=(Vehicle("v1", capacity, "D"), Vehicle("v2", capacity, "D")),
    )
