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

## Hybrid QPSO-inspired optimizer (`qpso.py`, id `qpso_hybrid`, v1)

**Not canonical QPSO.** The update rule in step 6 is the standard QPSO position update (Sun,
Feng & Xu 2004, with the mean-best attractor of Sun et al. 2004). It acts on a continuous
*latent* key vector. Everything that turns keys into routes is a discrete, problem-specific
layer: decoding, repair, local search and Lamarckian write-back. The overall method is
therefore a hybrid metaheuristic inspired by QPSO, not QPSO itself.

"Quantum" refers only to the delta-potential-well sampling distribution that motivates the
update. Nothing runs on quantum hardware, and no quantum speedup is claimed.

Notation:
- n customers, V vehicles, swarm of M particles, iteration t = 0..T-1.
- U(a, b) is a uniform draw from the seeded RNG.

### 1. Encoding
Each particle i has a position `x_i ∈ R^(2n)`:
- **Assignment keys** `a_i = x_i[0:n]`, kept in `[0, V)`.
- **Order keys** `o_i = x_i[n:2n]`, kept in `[0, 1]`.

### 2. Decoding (keys → routes)
- Customer k goes to vehicle `v(k) = min(floor(a_k), V-1)`.
- Each vehicle visits its customers in ascending `o_k`, ties broken by customer index.
- The decoding is deterministic.
- Encoding a route set S as `a_k = v + 0.5`, `o_k = (rank_k + 0.5) / |route_v|` gives
  `decode(encode(S)) = S` exactly. Write-back (step 8) relies on this.

### 3. Feasible assignment by repair
The decoded routes can exceed capacity or contain unreachable legs. Repair works in two steps:

a. **Remove customers.**
   - While a vehicle is over capacity, remove the customer whose removal saves the most travel time, ties to the lower index.
   - While a route has an unreachable leg, remove the customer whose removal reduces the number of unreachable legs most, ties to the larger saving.

b. **Reinsert** each removed customer, largest demand first, at the cheapest position over all vehicles that keeps the route within capacity and all legs reachable (same rule as `cheapest_insertion`).

If some customer has no such position, the particle is **infeasible**. Its energy is then
`E = travel(S) + λ·overload(S)` (λ as in SA), with unplaceable customers forced into the
least-overloaded reachable position. If no reachable position exists at all, `E = +∞`.
Infeasible particles can be personal or global bests only while no feasible particle exists
(step 4), and they never become the reported incumbent.

### 4. Fitness and comparison
Particles are compared by `(infeasible, E)` in lexicographic order, so any feasible particle
beats any infeasible one. For a feasible particle `E = travel(S)`, the pure travel-time
objective.

### 5. Personal and global best
- `pbest_i`: the best position particle i has visited (after write-back), with its fitness.
- `gbest`: the best of all `pbest_i`.
- `mbest = (1/M) Σ_i pbest_i`: the mean-best position, element-wise.
- The incumbent is the best **feasible** decoded solution seen; its routes are stored separately.

### 6. Quantum-inspired update (canonical QPSO form, per particle i and dimension d)
```
φ ~ U(0,1)
p_d = φ · pbest_i,d + (1 − φ) · gbest_d                      (local attractor)
u ~ U(0,1],  s = +1 or −1 with probability 1/2
x_i,d ← p_d + s · β_t · |mbest_d − x_i,d| · ln(1/u)
```
- **β_t**, the contraction–expansion coefficient, decreases linearly from `beta_start` (1.0) to `beta_end` (0.5) over the iteration budget: `β_t = beta_start − (beta_start − beta_end)·t/(T−1)`.
  - Large β widens the sampling around p (exploration).
  - Small β contracts the swarm toward its attractors (exploitation).
  - For β below about 1.78 the canonical analysis gives convergence of the particle to p.
- **φ** sets where the attractor lies on the segment between the personal and global best.
- **ln(1/u)** gives the heavy-tailed jump lengths of the delta-well model.
- **|mbest − x|** scales each jump by the particle's distance from the swarm's mean best, which shrinks as the swarm converges.
- Positions are clipped back to the key boxes in step 1: `[0, V − 1e-9]` and `[0, 1]`.

### 7. Contraction–expansion actually implemented
Only the linear β schedule above. There is no adaptive β, no restarts, and no mutation of the
attractor. The swarm-diversity diagnostic `mean_d |x − mbest|` is recorded but not used for
control.

### 8. Discrete operators (hybrid part)
After decoding and repair, a feasible particle's routes get first-improvement local search
for at most `local_search_passes` passes (default 1; 0 disables it). Within a pass, each
operator below is applied repeatedly until it finds no improving move. The search stops early
if a whole pass improves nothing. The operators are:
- **relocate:** move a customer to another position, in the same or another route.
- **swap:** exchange two customers.
- **2-opt reversal:** reverse a segment within one route, with the reversed segment fully re-costed on the directed graph.

Every move is applied only if the new routes are within capacity, all legs are reachable, and
travel time strictly decreases. So the operators preserve feasibility rather than repair it.

The improved routes are written back into the particle (`x_i ← encode(S)`): Lamarckian
learning, `lamarckian: true` by default. Without write-back, the keys keep their pre-search
values, and the fitness and incumbent still use the improved routes.

### 9. Infeasible solutions
- Their energy is penalised (step 3).
- They rank below every feasible solution (step 4).
- They are never the incumbent.
- The run ends `no_solution_found` if no feasible solution was ever decoded. A scenario proven infeasible before search (capacity or reachability) ends `infeasible_scenario` without searching.

### 10. Termination and budget
- **Budget:** `iterations` swarm updates (default 100) × `swarm_size` particles (default 20), plus the initial swarm.
- **Other stops:**
  - `time_limit_s` (optional; makes results machine-dependent)
  - `max_no_improvement` iterations without a better incumbent
  - cancellation, checked before each particle evaluation
- **Initial swarm:** particle 0 is `encode(cheapest_insertion)` when `seed_with_construction` (default true). The rest are uniform in the key boxes.
- **Evaluations:** one per particle decode (decode + repair) plus one per local-search move tried.
- **Determinism:** all randomness uses `random.Random(seed)`. A generated seed is recorded.

### Ablation hook
`update_rule: "uniform_resample"` replaces step 6 with independent uniform resampling of every
key, keeping decode, repair and local search unchanged. It is an **ablation baseline for
experiments only**: it measures how much the QPSO update contributes beyond decode + repair +
local search. It is not the algorithm, and the default is `"qpso"`.

### Tests of the formulation (`tests/unit/test_qpso.py`)
- **Encoding:** `decode(encode(S)) = S` on 200 random route sets; decoding tie and boundary rules.
- **Update rule:**
  - stationary when `x = pbest = gbest = mbest`;
  - with β = 0, samples lie on the [pbest, gbest] segment with mean at the midpoint;
  - `E|x' − p| = β·|mbest − x|` and the sign is symmetric (40k samples);
  - deterministic for a given RNG state.
- **Repair:**
  - fixes capacity and unreachable legs;
  - leaves feasible routes unchanged;
  - reports failure on an unpackable instance, where the run ends `no_solution_found` instead of returning a fake solution.
- **Local search:** never worsens, stays feasible, and its result is a local optimum.
- **Whole optimizer:**
  - deterministic per seed;
  - evaluator parity;
  - cancellation keeps the incumbent;
  - every stopping rule;
  - swarm diversity contracts under QPSO but not under resampling.

### Measured ablation (2026-10-28, this machine)
Command: `uv run python -m trafiqon.experiments.ablation_qpso --seeds 5`.

Setup:
- Both rules use the same decode, repair and local search, and the same swarm size and iteration count, so particle evaluations are equal.
- Without local search: 20 particles × 100 iterations. With local search: 15 × 30.
- Mean objective in minutes, n = 5 seeds.
- Gap is relative to the best objective observed in the experiment, a heuristic reference, not an optimum.

| Scenario | qpso / no-ls | resample / no-ls | qpso / ls | resample / ls |
|---|---|---|---|---|
| congested_city (small) | 74.66 (gap 1.17 %) | 77.80 (5.42 %) | 73.80 (0.00 %) | 73.80 (0.00 %) |
| experimental_grid_s0_n30 | 261.66 (23.61 %) | 277.14 (30.92 %) | 211.76 (0.04 %) | 212.93 (0.59 %) |

Reading:
- The QPSO update gave lower mean objectives than uniform resampling in three of the four settings and tied in the fourth, at equal particle evaluations. The gap is clearest when local search is off.
- With local search on, most of the improvement comes from local search: no-ls means are 23–31 % above the reference, ls means 0–0.6 %.
- n = 5 per setting and no significance test was run. Treat this as evidence that the update is not inert, not as a performance claim.

### Limitations
- Local search dominates the cost. On the 30-customer instance a run of 15 × 30 particles takes about 5 s, against about 0.2 s for SA at its default budget, which reached a similar objective (211.8). The hybrid is not faster than SA on these instances.
- The assignment keys use a floor map, so small key moves near integer boundaries jump between vehicles. The key space does not encode route adjacency, so the QPSO update searches a landscape that is only partly correlated with route cost. Local search does much of the fine-grained work.
- The Lamarckian write-back changes the dynamics compared with canonical QPSO: positions jump to encoded local optima.
- Results are only compared on small synthetic fixtures. There is no claim of superiority over OR-Tools or SA.
