# Mathematical model (as implemented, M1)

Code: `backend/src/trafiqon/domain`, `backend/src/trafiqon/routing`.

## Network
Directed multigraph G = (V, E). Each edge e = (u, v) has `distance` (km), `base_time` and
`current_time` (minutes), a `closed` flag, and optional `road_class`, `capacity`, `congestion`.
Parallel edges are allowed; self-loops and negative or non-finite values are rejected.
Only open edges can be traversed. Routing cost is `current_time`; `base_time` is the
free-flow reference that traffic changes scale. Graphs are immutable: closures and traffic
changes (`Graph.with_edge_closed`, `with_edge_time`, `with_edges`) return a new graph.

## Scenario
Depots (node), customers (node, integer demand > 0), vehicles (integer capacity > 0,
start depot, allowed end depots; empty means "return to start"). Customers may not sit on
depot nodes. `validate_scenario` reports structural errors (reject) separately from
capacity infeasibility (a single demand above the largest capacity, or total demand above
total capacity), which is reported but not rejected.

## Shortest paths
- Dijkstra: binary heap, nonnegative weights, ties broken by node id (deterministic).
- A*: `h(n) = euclid(n, t) / v_max`, with `v_max = max over open edges of euclid(u, v) /
  current_time(u, v)`. For every open edge `current_time >= euclid(u, v) / v_max`, so by
  the triangle inequality h never overestimates (admissible) and `h(u) <= c(u, v) + h(v)`
  (consistent). It is recomputed per query from current conditions. If any node lacks
  coordinates, or an open edge has zero time but nonzero length (v_max unbounded), A* uses
  h = 0 (i.e. Dijkstra). Tests assert A* cost == Dijkstra cost on every node pair of every
  fixture and on 400 random graphs, and check admissibility/consistency on fixtures.
- Path reconstruction follows predecessor edges (not predecessor nodes), so parallel edges
  are reconstructed exactly; every returned path lists both node ids and edge ids.

## Cost matrix
Locations = distinct depot and customer nodes. One Dijkstra tree per location gives the
directed matrix `time[i, j]`, `distance[i, j]` and the edge-level path for each ordered pair
(used to draw routes). Unreachable pairs have `reachable[i, j] = False` and NaN costs. There
is no big-M substitute. `check_reachability` flags customers that no vehicle (with enough
capacity) can reach from its start depot and return from to an allowed end depot.

## Solution and objective
A solution is a set of vehicle routes: start depot, ordered customers, end depot, and
optionally explicit edge paths per leg. Without explicit legs, each leg is the shortest
path under current conditions.

Objective: f(S) = sum over routes, over traversed edges, of `current_time`. Total distance is
reported separately. `evaluate_solution` is the single evaluator for every algorithm and
checks the following:
- every customer is served exactly once (missing, duplicate and unknown customers are reported);
- load <= capacity;
- each route starts at the vehicle's start depot and ends at an allowed end depot;
- one route per vehicle;
- every leg is reachable;
- for explicit legs, every edge exists, is open, and the path is contiguous between the stops.

`feasible` is true only when no violations are found. `objective` is reported whenever every
leg resolves, even if capacity or coverage is violated (for diagnostics). It is `None` if any
leg is unreachable or invalid, so an invalid route never gets a cost. Callers must show
`feasible` alongside the objective.

## Not yet modelled
Time windows, heterogeneous costs per vehicle, and route-stability penalties are not
modelled. Incidents are currently represented only as closed edges plus metadata in
`Scenario.settings`. The incident lifecycle comes in M7.
