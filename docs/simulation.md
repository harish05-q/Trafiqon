# Simulation (as implemented, M7)

Code: `backend/src/trafiqon/simulation/` (pure Python, no framework imports) and
`backend/src/trafiqon/api/routers/simulations.py`. UI: Command Center → Simulation panel.

## Clock
- **Ticks:** discrete ticks of `tick_minutes` (default 0.5 simulated minutes). `time = tick × tick_minutes`, so floating-point drift never accumulates.
- **Within a tick:** each vehicle spends exactly the tick's time budget along its plan.
  - Partial edge traversal, arrivals and stop completions happen at exact intra-tick times.
  - Zero-time transitions happen even when the budget is spent: completing a stop on arrival, finishing at the depot, being blocked. A stop reached exactly at a tick boundary is therefore completed in that tick.
- **Tick size:** results do not depend on the tick size. This is tested for 0.1 to 3 minutes.
- **Real-time playback** (`SimulationSession`):
  - While running, simulated time advances at `speed` simulated minutes per wall-clock second (0.25 to 30).
  - Each request converts elapsed wall time into **whole ticks** and carries the remainder. The engine therefore only ever sees whole ticks, and the state is a deterministic function of the tick at which each command was applied; every command is in the event log with its tick.
  - At most 20,000 ticks are applied per request.
  - Paused or ready sessions do not advance with wall time.

## Vehicle state
Each vehicle has:
- a position: either a node, or an edge with a `progress` value in [0, 1];
- a remaining plan: a list of legs, each with a stop and a path of edges, ending with a leg to the end depot;
- the index of the next edge to enter, completed stops with their times, and stops reported as unserved;
- simulated distance, driving time and delivered load.

Statuses:
- `en_route`
- `blocked`: the next planned edge is closed, or the vehicle is stranded away from its depot.
- `finished`: at the end depot with no legs left.
- `idle`: no route.

The simulation is `finished` only when every vehicle is finished or idle. A stranded vehicle keeps it `running`, honestly.

The initial plan is either a completed run's stored solution, simulated along exactly the shared evaluator's leg paths, or a deterministic cheapest-insertion plan. Infeasible solutions are rejected. When nothing changes, a vehicle's simulated driving time equals the run's evaluator objective (an integration test checks this).

## Road conditions
Effective edge = original edge, then manual traffic factor, then manual closure, then active incidents:
- a `closure` incident closes the edge;
- a `slowdown` incident multiplies its travel time (factors compose).

Resolving an incident or clearing a factor recomputes the edge from these layers, so effects never leak.

### Effect on a vehicle already on an edge
- **Traffic change:** the vehicle **keeps its progress**, and the remaining `(1 − progress) × current_time` is re-timed at the new speed. The part already driven is not re-timed.
- **Closure:** closures stop vehicles from **entering** an edge. A vehicle already on the edge finishes it.
- **Closed next edge:** a vehicle whose next planned edge is closed waits at the node (`blocked`). It continues on its own if the road reopens, or takes a new path after a replan.

## Replanning (`replan`)
- **Preserved:** the clock, every completed stop and every vehicle's position. A vehicle on an edge finishes that edge, and its new plan starts at the edge's target node.
- **Scope:** each vehicle keeps its own remaining customers, plus any previously unserved ones, which are retried. Goods are on board, so customers are not moved between vehicles.
- **Order:** the visiting order and all paths are recomputed on current conditions with directed shortest paths.
  - Up to 7 stops: exact (all permutations). A test shows the result is never worse than keeping the old order.
  - More than 7 stops: cheapest insertion plus 2-opt.
- **Unreachable stops:** reported as `unserved`, never given a cost. If the end depot is unreachable, the vehicle is reported as stranded; it still serves stops at its own node and waits.
- **Metrics:** `latency_ms` is measured wall time. `stops_reordered`, `edges_changed` and `remaining_time_min` are derived disruption and cost figures. The report labels each quantity kind.

## API (`/api/v1/simulations`)
- `POST` creates a session: `{scenario_version_id, run_id?, tick_minutes, speed}`.
- `GET /{id}` returns the authoritative state:
  - each vehicle's position, with `x`/`y` computed on the server, and its remaining edges;
  - incidents and road overrides;
  - the last 50 events and the last replan report;
  - served count and quantity kinds.
- `POST /{id}/control` takes `start|pause|resume|step|reset|speed`. Commands that don't fit the current status return 409.
- `POST /{id}/incidents` creates an incident; `POST /{id}/incidents/{iid}/resolve` resolves it.
- `POST /{id}/roads` takes `{edge_id, closed?, traffic_factor?}`.
- `POST /{id}/replan` replans and returns the report and the new state.
- `DELETE /{id}` deletes the session.

Sessions are held **in the API process's memory** (decision D27). They are bounded by `max_simulations`, expire after an idle TTL, are not persisted frame by frame, and are lost on an API restart; the UI says so if its session has gone. They assume a single API process.

## Frontend
- The Command Center polls the state every 400 ms while running. It draws vehicles at the backend's positions, each vehicle's remaining planned path, and the current road conditions.
- A 400 ms CSS transition smooths markers between updates. This interpolation is the only thing the frontend adds, and it is disabled under `prefers-reduced-motion`. No state transition is invented on the client.
