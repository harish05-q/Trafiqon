"""Plain-dict (JSON-compatible) conversion for scenarios. Used by fixtures, API, persistence."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from trafiqon.domain.models import Customer, Depot, Edge, Graph, Node, Scenario, Vehicle


def graph_to_dict(graph: Graph) -> dict[str, Any]:
    return {
        "nodes": [{"id": n.id, "x": n.x, "y": n.y, "label": n.label} for n in graph.nodes.values()],
        "edges": [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "distance": e.distance,
                "base_time": e.base_time,
                "current_time": e.current_time,
                "closed": e.closed,
                "road_class": e.road_class,
                "capacity": e.capacity,
                "congestion": e.congestion,
            }
            for e in graph.edges.values()
        ],
    }


def graph_from_dict(data: dict[str, Any]) -> Graph:
    nodes = [
        Node(id=n["id"], x=n.get("x"), y=n.get("y"), label=n.get("label")) for n in data["nodes"]
    ]
    edges = [
        Edge(
            id=e["id"],
            source=e["source"],
            target=e["target"],
            distance=float(e["distance"]),
            base_time=float(e["base_time"]),
            current_time=float(e.get("current_time", e["base_time"])),
            closed=bool(e.get("closed", False)),
            road_class=e.get("road_class"),
            capacity=e.get("capacity"),
            congestion=e.get("congestion"),
        )
        for e in data["edges"]
    ]
    return Graph(nodes, edges)


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
        "synthetic": scenario.synthetic,
        "settings": dict(scenario.settings),
        "graph": graph_to_dict(scenario.graph),
        "depots": [{"id": d.id, "node_id": d.node_id} for d in scenario.depots],
        "customers": [
            {"id": c.id, "node_id": c.node_id, "demand": c.demand} for c in scenario.customers
        ],
        "vehicles": [
            {
                "id": v.id,
                "capacity": v.capacity,
                "start_depot_id": v.start_depot_id,
                "end_depot_ids": list(v.end_depot_ids),
            }
            for v in scenario.vehicles
        ],
    }


def scenario_from_dict(data: dict[str, Any]) -> Scenario:
    return Scenario(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        synthetic=bool(data.get("synthetic", True)),
        settings=dict(data.get("settings", {})),
        graph=graph_from_dict(data["graph"]),
        depots=tuple(Depot(id=d["id"], node_id=d["node_id"]) for d in data["depots"]),
        customers=tuple(
            Customer(id=c["id"], node_id=c["node_id"], demand=int(c["demand"]))
            for c in data["customers"]
        ),
        vehicles=tuple(
            Vehicle(
                id=v["id"],
                capacity=int(v["capacity"]),
                start_depot_id=v["start_depot_id"],
                end_depot_ids=tuple(v.get("end_depot_ids", ())),
            )
            for v in data["vehicles"]
        ),
    )


def scenario_fingerprint(scenario: Scenario) -> str:
    """SHA-256 of the canonical JSON form; identical content gives an identical fingerprint."""
    canonical = json.dumps(scenario_to_dict(scenario), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
