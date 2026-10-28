"""Deterministic built-in scenarios. All are SYNTHETIC: generated grids, not real road data.

Generated from fixed arithmetic (no RNG), so they are identical across platforms and versions.
Units: x/y and distance in km, times in minutes, speeds in km/h.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from trafiqon.domain.models import Customer, Depot, Edge, Graph, Node, Scenario, Vehicle
from trafiqon.domain.validation import require_valid

ARTERIAL_KMH = 48.0
LOCAL_KMH = 30.0
RING_KMH = 60.0


def node_id(r: int, c: int) -> str:
    return f"n{r}_{c}"


def edge_id(u: str, v: str) -> str:
    return f"{u}->{v}"


def _grid(
    rows: int,
    cols: int,
    *,
    spacing: float = 1.0,
    speed_kmh: Callable[[tuple[int, int], tuple[int, int]], tuple[float, str]],
    allowed: Callable[[tuple[int, int], tuple[int, int]], bool] = lambda a, b: True,
    congestion: Callable[[tuple[int, int], tuple[int, int]], float] = lambda a, b: 1.0,
    closed: frozenset[str] = frozenset(),
) -> Graph:
    nodes = [
        Node(node_id(r, c), x=c * spacing, y=r * spacing, label=f"{r},{c}")
        for r in range(rows)
        for c in range(cols)
    ]
    edges: list[Edge] = []
    for r in range(rows):
        for c in range(cols):
            for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                r2, c2 = r + dr, c + dc
                if not (0 <= r2 < rows and 0 <= c2 < cols):
                    continue
                a, b = (r, c), (r2, c2)
                if not allowed(a, b):
                    continue
                u, v = node_id(r, c), node_id(r2, c2)
                # Road length >= straight line: deterministic 0-15% detour factor.
                distance = round(
                    spacing * (1.0 + 0.05 * ((3 * min(r, r2) + 5 * min(c, c2)) % 4)), 3
                )
                kmh, road_class = speed_kmh(a, b)
                base_time = round(distance / kmh * 60.0, 3)
                factor = congestion(a, b)
                eid = edge_id(u, v)
                edges.append(
                    Edge(
                        id=eid,
                        source=u,
                        target=v,
                        distance=distance,
                        base_time=base_time,
                        current_time=round(base_time * factor, 3),
                        closed=eid in closed,
                        road_class=road_class,
                        congestion=factor,
                    )
                )
    return Graph(nodes, edges)


def urban_grid() -> Scenario:
    """6x5 grid, one depot, 10 customers, 3 vehicles. Arterials on row 2 and column 2;
    the perimeter is a one-way clockwise loop."""
    rows, cols = 6, 5

    def speed(a, b):
        same_row, same_col = a[0] == b[0], a[1] == b[1]
        if (same_row and a[0] == 2) or (same_col and a[1] == 2):
            return ARTERIAL_KMH, "arterial"
        return LOCAL_KMH, "local"

    def allowed(a, b):
        if a[0] == b[0] == 0:
            return b[1] > a[1]  # row 0 eastbound only
        if a[0] == b[0] == rows - 1:
            return b[1] < a[1]  # last row westbound only
        if a[1] == b[1] == 0:
            return b[0] < a[0]  # column 0 decreasing row only
        if a[1] == b[1] == cols - 1:
            return b[0] > a[0]  # last column increasing row only
        return True

    graph = _grid(rows, cols, speed_kmh=speed, allowed=allowed)
    customers = [
        ("c01", (0, 1), 4), ("c02", (0, 4), 3), ("c03", (1, 3), 5), ("c04", (3, 0), 2),
        ("c05", (3, 4), 4), ("c06", (4, 1), 3), ("c07", (5, 3), 6), ("c08", (5, 0), 2),
        ("c09", (1, 1), 3), ("c10", (4, 3), 4),
    ]  # fmt: skip
    return require_valid(
        Scenario(
            id="urban_grid",
            name="Urban Grid",
            description="Synthetic 6x5 street grid with two arterials and one-way perimeter.",
            graph=graph,
            depots=(Depot("d1", node_id(2, 2)),),
            customers=tuple(Customer(i, node_id(*rc), d) for i, rc, d in customers),
            vehicles=tuple(Vehicle(f"v{k}", 15, "d1") for k in (1, 2, 3)),
            settings={"units": {"time": "min", "distance": "km"}, "incidents": []},
        )
    )


def congested_city() -> Scenario:
    """6x6 grid with a fast ring road and a congested core (x2.5 travel time).
    Two depots, 12 customers, 4 vehicles."""
    rows = cols = 6

    def on_ring(a, b):
        return (a[0] == b[0] and a[0] in (0, rows - 1)) or (a[1] == b[1] and a[1] in (0, cols - 1))

    def speed(a, b):
        return (RING_KMH, "ring") if on_ring(a, b) else (LOCAL_KMH, "local")

    def in_core(p):
        return 2 <= p[0] <= 3 and 2 <= p[1] <= 3

    def congestion(a, b):
        return 2.5 if in_core(a) or in_core(b) else 1.0

    def allowed(a, b):
        if a[1] == b[1] == 1:
            return b[0] > a[0]  # column 1 one-way
        if a[1] == b[1] == 4:
            return b[0] < a[0]  # column 4 one-way, opposite direction
        return True

    graph = _grid(rows, cols, speed_kmh=speed, allowed=allowed, congestion=congestion)
    customers = [
        ("c01", (0, 3), 3), ("c02", (1, 1), 4), ("c03", (1, 4), 2), ("c04", (2, 2), 5),
        ("c05", (2, 5), 3), ("c06", (3, 0), 4), ("c07", (3, 3), 2), ("c08", (4, 1), 3),
        ("c09", (4, 4), 4), ("c10", (5, 2), 3), ("c11", (2, 3), 2), ("c12", (5, 0), 4),
    ]  # fmt: skip
    return require_valid(
        Scenario(
            id="congested_city",
            name="Congested City",
            description="Synthetic 6x6 grid: 60 km/h ring road, congested core at 2.5x base time.",
            graph=graph,
            depots=(Depot("d1", node_id(0, 0)), Depot("d2", node_id(5, 5))),
            customers=tuple(Customer(i, node_id(*rc), d) for i, rc, d in customers),
            vehicles=(
                Vehicle("v1", 12, "d1"),
                Vehicle("v2", 12, "d1"),
                Vehicle("v3", 12, "d2"),
                Vehicle("v4", 12, "d2"),
            ),
            settings={
                "units": {"time": "min", "distance": "km"},
                "congestion": {"core_factor": 2.5},
                "incidents": [],
            },
        )
    )


INCIDENT_EDGES = (
    edge_id(node_id(2, 1), node_id(2, 2)),
    edge_id(node_id(2, 2), node_id(2, 1)),
    edge_id(node_id(1, 2), node_id(2, 2)),
)


def incident_response() -> Scenario:
    """5x5 grid with an active incident closing three road segments around n2_2.
    One depot, 8 customers, 3 vehicles."""

    def speed(a, b):
        same_row, same_col = a[0] == b[0], a[1] == b[1]
        if (same_row and a[0] == 0) or (same_col and a[1] == 0):
            return ARTERIAL_KMH, "arterial"
        return LOCAL_KMH, "local"

    graph = _grid(5, 5, speed_kmh=speed, closed=frozenset(INCIDENT_EDGES))
    customers = [
        ("c01", (0, 4), 3), ("c02", (1, 2), 4), ("c03", (2, 2), 2), ("c04", (2, 4), 5),
        ("c05", (3, 1), 3), ("c06", (4, 0), 2), ("c07", (4, 3), 4), ("c08", (3, 3), 3),
    ]  # fmt: skip
    return require_valid(
        Scenario(
            id="incident_response",
            name="Incident Response",
            description="Synthetic 5x5 grid with a collision closing three segments at n2_2.",
            graph=graph,
            depots=(Depot("d1", node_id(0, 0)),),
            customers=tuple(Customer(i, node_id(*rc), d) for i, rc, d in customers),
            vehicles=tuple(Vehicle(f"v{k}", 10, "d1") for k in (1, 2, 3)),
            settings={
                "units": {"time": "min", "distance": "km"},
                "incidents": [
                    {"id": "inc-1", "kind": "collision", "edge_ids": list(INCIDENT_EDGES)}
                ],
            },
        )
    )


BUILTIN_SCENARIOS: dict[str, Callable[[], Scenario]] = {
    "urban_grid": urban_grid,
    "congested_city": congested_city,
    "incident_response": incident_response,
}


def load_builtin(scenario_id: str) -> Scenario:
    try:
        factory = BUILTIN_SCENARIOS[scenario_id]
    except KeyError:
        raise KeyError(f"unknown built-in scenario {scenario_id!r}") from None
    return factory()


def experimental_grid(seed: int = 0, size: int = 7, n_customers: int = 30) -> Scenario:
    """LARGER-EXPERIMENTAL synthetic instance for benchmarks (not a built-in UI scenario).

    size x size grid, random one-way streets and congestion from `random.Random(seed)`,
    `n_customers` customers with demand 1-6, one central depot, capacity-tight fleet of 15.
    Regenerated identically for the same arguments.
    """
    rng = random.Random(seed)
    one_way = {
        (r, c, rng.random() < 0.5) for r in range(size) for c in range(size) if rng.random() < 0.25
    }
    one_way_dir = {(r, c): east for r, c, east in one_way}
    factors = {
        (r, c): round(1.0 + 1.5 * rng.random() ** 3, 2) for r in range(size) for c in range(size)
    }

    def speed(a, b):
        return (
            (ARTERIAL_KMH, "arterial")
            if size // 2 in (a[0], a[1]) and size // 2 in (b[0], b[1])
            else (LOCAL_KMH, "local")
        )

    def allowed(a, b):
        # A one-way flag on cell a restricts its horizontal outgoing edge to one direction.
        if a[0] == b[0] and a in one_way_dir:
            return (b[1] > a[1]) == one_way_dir[a]
        return True

    def congestion(a, b):
        return factors[a]

    graph = _grid(size, size, speed_kmh=speed, allowed=allowed, congestion=congestion)
    depot = (size // 2, size // 2)
    cells = [(r, c) for r in range(size) for c in range(size) if (r, c) != depot]
    rng.shuffle(cells)
    customers = [
        Customer(f"c{i + 1:02d}", node_id(*cells[i]), rng.randint(1, 6)) for i in range(n_customers)
    ]
    total = sum(c.demand for c in customers)
    n_vehicles = -(-total * 10 // (15 * 9))  # ~90% fleet utilisation
    return require_valid(
        Scenario(
            id=f"experimental_grid_s{seed}_n{n_customers}",
            name=f"Experimental grid (seed {seed}, {n_customers} customers)",
            description="Larger-experimental synthetic grid; random one-ways and congestion.",
            graph=graph,
            depots=(Depot("d1", node_id(*depot)),),
            customers=tuple(customers),
            vehicles=tuple(Vehicle(f"v{k + 1}", 15, "d1") for k in range(n_vehicles)),
            settings={"units": {"time": "min", "distance": "km"}, "class": "larger-experimental"},
        )
    )
