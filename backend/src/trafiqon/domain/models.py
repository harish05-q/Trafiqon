"""Core domain entities: directed road graph, depots, customers, fleet, scenario.

Units: travel times in minutes, distances in kilometres, demand/capacity in integer units.
All entities are immutable; changes to traffic or closures produce a new Graph.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    x: float | None = None
    y: float | None = None
    label: str | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.x is not None and self.y is not None


@dataclass(frozen=True, slots=True)
class Edge:
    """A directed road segment. `current_time` is the cost used for routing."""

    id: str
    source: str
    target: str
    distance: float
    base_time: float
    current_time: float
    closed: bool = False
    road_class: str | None = None
    capacity: float | None = None
    congestion: float | None = None

    @property
    def is_open(self) -> bool:
        return not self.closed


class GraphError(ValueError):
    """Raised when a graph is structurally invalid."""


class Graph:
    """Immutable directed multigraph. Parallel edges are allowed, self-loops are not."""

    __slots__ = ("_edges", "_in", "_nodes", "_out")

    def __init__(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        node_map: dict[str, Node] = {}
        for node in nodes:
            if node.id in node_map:
                raise GraphError(f"duplicate node id {node.id!r}")
            node_map[node.id] = node

        edge_map: dict[str, Edge] = {}
        out_adj: dict[str, list[Edge]] = {n: [] for n in node_map}
        in_adj: dict[str, list[Edge]] = {n: [] for n in node_map}
        for edge in edges:
            if edge.id in edge_map:
                raise GraphError(f"duplicate edge id {edge.id!r}")
            if edge.source not in node_map:
                raise GraphError(f"edge {edge.id!r} source {edge.source!r} is not a node")
            if edge.target not in node_map:
                raise GraphError(f"edge {edge.id!r} target {edge.target!r} is not a node")
            if edge.source == edge.target:
                raise GraphError(f"edge {edge.id!r} is a self-loop")
            for name in ("distance", "base_time", "current_time"):
                value = getattr(edge, name)
                if not math.isfinite(value) or value < 0:
                    raise GraphError(f"edge {edge.id!r} {name} must be finite and >= 0")
            edge_map[edge.id] = edge
            out_adj[edge.source].append(edge)
            in_adj[edge.target].append(edge)

        self._nodes = MappingProxyType(node_map)
        self._edges = MappingProxyType(edge_map)
        # Deterministic iteration order regardless of input order.
        self._out = {n: tuple(sorted(es, key=lambda e: e.id)) for n, es in out_adj.items()}
        self._in = {n: tuple(sorted(es, key=lambda e: e.id)) for n, es in in_adj.items()}

    @property
    def nodes(self) -> Mapping[str, Node]:
        return self._nodes

    @property
    def edges(self) -> Mapping[str, Edge]:
        return self._edges

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def out_edges(self, node_id: str, *, include_closed: bool = False) -> tuple[Edge, ...]:
        edges = self._out[node_id]
        return edges if include_closed else tuple(e for e in edges if e.is_open)

    def in_edges(self, node_id: str, *, include_closed: bool = False) -> tuple[Edge, ...]:
        edges = self._in[node_id]
        return edges if include_closed else tuple(e for e in edges if e.is_open)

    def with_edges(self, updated: Iterable[Edge]) -> Graph:
        """Return a new graph with the given edges replaced by id (traffic, closures)."""
        changes = {e.id: e for e in updated}
        unknown = set(changes) - set(self._edges)
        if unknown:
            raise GraphError(f"unknown edge ids {sorted(unknown)}")
        return Graph(self._nodes.values(), (changes.get(i, e) for i, e in self._edges.items()))

    def with_edge_closed(self, edge_id: str, closed: bool = True) -> Graph:
        return self.with_edges([replace(self._edges[edge_id], closed=closed)])

    def with_edge_time(self, edge_id: str, current_time: float) -> Graph:
        return self.with_edges([replace(self._edges[edge_id], current_time=current_time)])


@dataclass(frozen=True, slots=True)
class Depot:
    id: str
    node_id: str


@dataclass(frozen=True, slots=True)
class Customer:
    id: str
    node_id: str
    demand: int


@dataclass(frozen=True, slots=True)
class Vehicle:
    """A vehicle starts at `start_depot_id` and must end at one of `end_depot_ids`.

    If `end_depot_ids` is empty the vehicle must return to its start depot.
    """

    id: str
    capacity: int
    start_depot_id: str
    end_depot_ids: tuple[str, ...] = ()

    @property
    def allowed_end_depots(self) -> tuple[str, ...]:
        return self.end_depot_ids or (self.start_depot_id,)


@dataclass(frozen=True, slots=True)
class Scenario:
    """A routing problem instance. Construct via `build_scenario` to get validation."""

    id: str
    name: str
    graph: Graph
    depots: tuple[Depot, ...]
    customers: tuple[Customer, ...]
    vehicles: tuple[Vehicle, ...]
    description: str = ""
    synthetic: bool = True
    settings: Mapping[str, Any] = field(default_factory=dict)

    def depot(self, depot_id: str) -> Depot:
        return _by_id(self.depots, depot_id, "depot")

    def customer(self, customer_id: str) -> Customer:
        return _by_id(self.customers, customer_id, "customer")

    def vehicle(self, vehicle_id: str) -> Vehicle:
        return _by_id(self.vehicles, vehicle_id, "vehicle")

    def with_graph(self, graph: Graph) -> Scenario:
        return replace(self, graph=graph)


def _by_id[T: (Depot, Customer, Vehicle)](items: tuple[T, ...], item_id: str, kind: str) -> T:
    for item in items:
        if item.id == item_id:
            return item
    raise KeyError(f"unknown {kind} {item_id!r}")
