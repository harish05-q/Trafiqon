# Algorithms (as implemented)

Code: `backend/src/trafiqon/optimization/`. The model, objective and evaluator are in
`mathematical_model.md`.

## Common contract (`contract.py`)
- **Input** (`AlgorithmInput`): scenario, config, seed, a progress callback, a cancel token, and an optional cached cost matrix (it must be built from `scenario.graph`).
- **Output** (`AlgorithmResult`): algorithm id and version, the resolved config and seed, best feasible solution, the shared-evaluator result, feasibility, objective, iterations, evaluations, elapsed time, time to first feasible, termination reason, optimality (`proven_optimal` / `not_proven`), best-so-far history, and diagnostics.
- **Reported numbers come from the shared evaluator.** `finalize` re-scores the candidate with `routing.evaluate_solution`.
  - If the evaluator rejects the candidate, it is not reported; its violations go into `diagnostics.rejected_candidate_violations`.
  - An algorithm's internal cost estimate is never reported as the objective.
- **Infeasible scenarios:** `problem.infeasibility_reasons` checks capacity and reachability before any search. If a reason is found, the run ends with `infeasible_scenario` and lists the reasons. It does not return a fake solution.
- **Progress events** carry iteration, evaluations, elapsed time, best feasible and current objective, and whether a feasible solution exists. There is no percentage field.
- **Cancellation** is cooperative (`CancelToken.is_cancelled()`). The best feasible incumbent found so far is kept and returned with reason `cancelled`.
- **Config:** unknown keys or out-of-range values raise `ConfigError`.

## Shared representation (`problem.py`)
- **Candidate:** one ordered list of customer indices per vehicle.
- **Route cost:** shortest-path time from the start depot, through the customers, to the cheapest allowed end depot. An empty route costs 0, because unused vehicles are omitted.
- **Unreachable legs:** these cost `+inf` inside the search, so the search rejects them. That value is never reported.
- **Parity test:** for 150 random assignments, internal cost equals the evaluator's objective.
- **Construction (`cheapest_insertion`):** deterministic. Customers are taken by descending demand, ties broken by id. Each goes into the cheapest position that keeps all vehicles within capacity and all legs reachable. If no such position exists, it goes where overload is smallest, and the caller must check `overload`.

## Simulated Annealing (`simulated_annealing.py`, id `simulated_annealing`, v1)
- **State:** the shared representation, starting from the cheapest-insertion construction.
- **Energy:** `E(S) = travel_time(S) + lambda * overload(S)`.
  - `overload` is the total demand above capacity, summed over vehicles.
  - `lambda` (`overload_penalty`, minutes per demand unit) defaults to 2 × the longest finite leg time.
  - The search may pass through capacity-infeasible states. Only overload-free states can become the incumbent.
  - The reported objective is the evaluator's pure travel time, never `E`.
- **Moves**, chosen uniformly among the enabled `moves`:
  - `relocate`: move one customer (picked uniformly) to a uniform position in a uniform vehicle's route, including its own route.
  - `swap`: exchange two customers, in the same or different routes.
  - `reverse`: reverse a random subsequence of one route. The route is re-costed in full, because a directed graph makes reversal asymmetric.
  - A move that creates an unreachable leg has infinite energy and is rejected.
- **Acceptance:** Metropolis. If dE ≤ 0 the move is accepted; otherwise it is accepted with probability `exp(-dE/T)`.
- **Temperature:**
  - `T0`: if not given, `T0 = -mean(dE+) / ln(p0)`, where dE+ are the positive deltas of `temperature_samples` random moves from the initial state and `p0 = initial_acceptance` (default 0.5).
  - Cooling is geometric, `T_k = T0 * alpha^k`. The default is `alpha = final_temperature_ratio^(1/max_iterations)`, so T reaches `T0 * 1e-3` at the iteration limit.
- **Stopping:**
  - `max_iterations` (default 20,000)
  - `time_limit_s` (optional; makes results machine-dependent)
  - `T < T0 * final_temperature_ratio` (only with an explicit `cooling_rate`)
  - `max_no_improvement`
  - cancellation, checked every 64 iterations
- **Determinism:** uses `random.Random(seed)`. With seed `None`, a seed is generated and recorded in the result; rerunning with it reproduces the run. The time limit is the only non-deterministic stopping rule.
- **Counting:** evaluations = 1 for the construction + temperature samples + one per proposed move, including rejected and inapplicable moves.

## OR-Tools CVRP (`ortools_cvrp.py`, id `ortools_cvrp`, v1, OR-Tools 9.15)
- **Model nodes:** depots, customers, and one dummy end per vehicle that has several allowed end depots. The arc into a dummy end costs the cheapest allowed end depot from that node.
- **Arc costs:** directed shortest-path times, scaled to integers (`cost_scale`, default 1000 per minute). The solver's integer objective is reported only as a diagnostic.
- **Unreachable arcs:** removed from `NextVar` domains (`removed_unreachable_arcs` in diagnostics). No big-M cost is used.
- **Capacity:** one dimension with per-vehicle capacities.
- **Search:**
  - First-solution strategy: `first_solution_strategy`, default `PATH_CHEAPEST_ARC`.
  - Improvement: `local_search_metaheuristic`, default `GUIDED_LOCAL_SEARCH`.
  - Limits: `time_limit_s` (default 2 s, required), optional `solution_limit`.
- **Progress and history:** one event per solution reported by OR-Tools. These may not improve, but best-so-far is tracked. Values are integer cost / scale.
- **Cancellation:** a `CustomLimit` search monitor polls the cancel token.
- **No seed:** the routing search takes no seed. Repeated time-limited runs can differ (`deterministic: false`). `evaluations` is `None`, because the solver exposes no comparable count.
- **Optimality:** `proven_optimal` only if the solver returns `ROUTING_OPTIMAL`, and that is optimality with respect to the integer-scaled costs. Time-limited GLS results are always `not_proven`. No exact method is implemented yet (optional in the spec).

## Hybrid QPSO-inspired optimizer
Not implemented yet (Milestone 3). This section will hold its formulation before any code is written.
