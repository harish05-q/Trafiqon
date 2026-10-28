"""Dijkstra and A* on the directed road graph, weighted by `Edge.current_time`.

Closed edges are never traversed. Ties are broken by node id so results are deterministic.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass

from trafiqon.domain.models import Edge, Graph

Heuristic = Callable[[str], float]


@dataclass(frozen=True, slots=True)
class Path:
    """An edge-level path. `edge_ids` is empty when source == target."""

    source: str
    target: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    travel_time: float
    distance: float


@dataclass(frozen=True, slots=True)
class SearchStats:
    expanded: int


@dataclass(frozen=True, slots=True)
class ShortestPathTree:
    """Single-source result: best time to each reached node and the edge used to reach it."""

    source: str
    time: dict[str, float]
    pred_edge: dict[str, Edge]
    stats: SearchStats

    def reachable(self, target: str) -> bool:
        return target in self.time

    def path_to(self, target: str) -> Path | None:
        if target not in self.time:
            return None
        return _reconstruct(self.source, target, self.pred_edge)


def _check_node(graph: Graph, node_id: str) -> None:
    if not graph.has_node(node_id):
        raise KeyError(f"unknown node {node_id!r}")


def _reconstruct(source: str, target: str, pred_edge: dict[str, Edge]) -> Path:
    edges: list[Edge] = []
    node = target
    while node != source:
        edge = pred_edge[node]
        edges.append(edge)
        node = edge.source
    edges.reverse()
    return Path(
        source=source,
        target=target,
        node_ids=(source, *(e.target for e in edges)),
        edge_ids=tuple(e.id for e in edges),
        travel_time=math.fsum(e.current_time for e in edges),
        distance=math.fsum(e.distance for e in edges),
    )


def dijkstra(graph: Graph, source: str, target: str | None = None) -> ShortestPathTree:
    """Single-source Dijkstra. Stops early once `target` is settled, if given."""
    _check_node(graph, source)
    if target is not None:
        _check_node(graph, target)
    time: dict[str, float] = {source: 0.0}
    pred_edge: dict[str, Edge] = {}
    settled: set[str] = set()
    heap: list[tuple[float, str]] = [(0.0, source)]
    expanded = 0
    while heap:
        d, node = heapq.heappop(heap)
        if node in settled:
            continue
        settled.add(node)
        expanded += 1
        if node == target:
            break
        for edge in graph.out_edges(node):
            nd = d + edge.current_time
            known = time.get(edge.target)
            if known is None or nd < known:
                time[edge.target] = nd
                pred_edge[edge.target] = edge
                heapq.heappush(heap, (nd, edge.target))
    # Drop tentative labels that were never settled (only possible with early stop).
    time = {n: t for n, t in time.items() if n in settled}
    pred_edge = {n: e for n, e in pred_edge.items() if n in settled}
    return ShortestPathTree(source, time, pred_edge, SearchStats(expanded))


def straight_line_heuristic(graph: Graph, target: str) -> Heuristic | None:
    """Admissible, consistent travel-time heuristic, or None if one cannot be established.

    Let v_max = max over open edges (u, v) of euclid(u, v) / current_time(u, v).
    Every open edge then satisfies current_time >= euclid(u, v) / v_max, so by the triangle
    inequality any path from n to target costs >= euclid(n, target) / v_max = h(n).
    The same inequality per edge gives consistency: h(u) <= current_time(u, v) + h(v).

    Returns None (caller should use the zero heuristic) when any node lacks coordinates or
    an open edge has zero travel time but nonzero straight-line length (v_max unbounded).
    """
    nodes = graph.nodes
    if not all(n.has_coordinates for n in nodes.values()):
        return None
    v_max = 0.0
    for edge in graph.edges.values():
        if edge.closed:
            continue
        a, b = nodes[edge.source], nodes[edge.target]
        length = math.hypot(a.x - b.x, a.y - b.y)  # type: ignore[operator]
        if length == 0:
            continue
        if edge.current_time == 0:
            return None
        v_max = max(v_max, length / edge.current_time)
    if v_max == 0:
        return None
    goal = nodes[target]

    def h(node_id: str) -> float:
        n = nodes[node_id]
        return math.hypot(n.x - goal.x, n.y - goal.y) / v_max  # type: ignore[operator]

    return h


def zero_heuristic(_node_id: str) -> float:
    return 0.0


def astar(
    graph: Graph, source: str, target: str, heuristic: Heuristic | None = None
) -> tuple[Path | None, SearchStats]:
    """A* search. Uses `straight_line_heuristic` when available, else the zero heuristic.

    The heuristic must be admissible; nodes may be reopened, so consistency is not required.
    """
    _check_node(graph, source)
    _check_node(graph, target)
    if heuristic is None:
        heuristic = straight_line_heuristic(graph, target) or zero_heuristic
    g: dict[str, float] = {source: 0.0}
    pred_edge: dict[str, Edge] = {}
    closed: dict[str, float] = {}
    heap: list[tuple[float, float, str]] = [(heuristic(source), 0.0, source)]
    expanded = 0
    while heap:
        _f, d, node = heapq.heappop(heap)
        if d > g[node]:
            continue  # stale entry
        if node in closed and closed[node] <= d:
            continue
        closed[node] = d
        expanded += 1
        if node == target:
            return _reconstruct(source, target, pred_edge), SearchStats(expanded)
        for edge in graph.out_edges(node):
            nd = d + edge.current_time
            known = g.get(edge.target)
            if known is None or nd < known:
                g[edge.target] = nd
                pred_edge[edge.target] = edge
                heapq.heappush(heap, (nd + heuristic(edge.target), nd, edge.target))
    return None, SearchStats(expanded)


def shortest_path(
    graph: Graph, source: str, target: str, algorithm: str = "dijkstra"
) -> Path | None:
    """Shortest travel-time path, or None if `target` is unreachable from `source`."""
    if algorithm == "dijkstra":
        return dijkstra(graph, source, target).path_to(target)
    if algorithm == "astar":
        return astar(graph, source, target)[0]
    raise ValueError(f"unknown algorithm {algorithm!r}")
