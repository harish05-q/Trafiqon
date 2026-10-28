# TRAFIQON Technical Spec (condensed)

Scope: directed, capacity-constrained VRP (CVRP) over a transportation graph, dynamic edge costs, incident-driven replanning. Do not present it as a solution to signal control, traffic assignment, or fleet dispatch in general.

## 1. Domain model
G = (V, E), directed. Edge fields: id, source, target, distance, base_time, current_time, closed flag, optional class and congestion metadata. Direction and closures are always respected.

Scenario: graph, depots, customers with demands, fleet (vehicles with capacity), traffic/incident settings, algorithm config. Scenario versions are immutable; a version referenced by a run or experiment is never mutated.

Objective: minimize total travel time, f(S) = sum of traversed edge travel times over all routes. Track distance, feasibility, and route disruption separately. Any stability penalty must be an explicit configurable component, with the pure travel-time objective reported independently.

CVRP formulation: build a directed customer-to-customer cost matrix from shortest paths under current conditions. Keep the edge-level path for each leg so routes can be drawn.

Constraints to validate: every customer served exactly once; load <= capacity; routes start and end at an allowed depot; every traversed edge exists and is open; every leg reachable. Unreachable pairs are reported as infeasible (or follow a documented policy). Never use an arbitrary big-M cost and present it as valid.

One evaluator, used by every algorithm. All displayed objective values must come from it, tied to a scenario version.

## 2. Routing
- Dijkstra (nonnegative weights, directed, closure-aware).
- A* with an admissible heuristic; zero heuristic when admissibility cannot be shown. Tests assert equal cost to Dijkstra.

## 3. Optimization
### 3.1 Common contract
Input: algorithm id and version, validated scenario, config, seed, progress callback, cancel signal. Output: best feasible solution (if any), objective, feasibility, evaluation/iteration history, elapsed time, termination reason, diagnostics.

### 3.2 OR-Tools baseline
Valid demands and capacities, explicit handling of unreachable legs and infeasible scenarios, time/search limits, solver status and metadata. A time-limited heuristic result is never called proven optimal. Optionally an exact method on small instances; record whether optimality was proven.

### 3.3 Simulated Annealing
Real SA: documented neighborhood moves, acceptance rule, temperature schedule, stopping conditions. Same representation, feasibility rules, and evaluator as the QPSO optimizer where practical.

### 3.4 Hybrid QPSO-inspired discrete optimizer
Write the math down first (`docs/algorithms.md`), then implement. Document:
1. Encoding (random-key encoding is a reasonable choice).
2. Decoding to customer orders and vehicle routes.
3. Feasible assignment construction or repair.
4. Personal-best state.
5. Global or neighborhood-best state.
6. The quantum-inspired update rule and the role of each parameter.
7. Local attractor / contraction-expansion, only if actually implemented.
8. Discrete operators (relocate, swap, 2-opt style reversal where directionality allows, cross-route reassign, feasible reinsertion). Each preserves or repairs feasibility.
9. Infeasible-solution treatment.
10. Termination and budget.

Seeded deterministic RNG. Retain best feasible incumbent. Track evaluations, iteration history, best-so-far, feasibility, elapsed time. Cooperative cancellation. Do not claim equivalence to canonical QPSO unless it truly implements it. If the update rule cannot be justified, stop and document the issue rather than substituting a generic metaheuristic.

### 3.5 Benchmarking
Same scenario version and comparable budgets across algorithms (explain any difference). Record: objective, feasibility and feasibility rate, wall time, time to first feasible, evaluation count, convergence history, replanning latency, post-incident route disruption, seed variance. Optimality gap only against a valid reference; define it precisely and distinguish proven optimum from heuristic reference. Report n, mean, median, std, best. Deterministic fixtures labeled small-synthetic vs larger-experimental. CSV and JSON export with reproducibility metadata. Label measured vs derived vs estimated vs simulated quantities.

## 4. Simulation
Deterministic discrete-time engine, independent of the frontend. State: sim time, tick, per-vehicle position (node or in-progress edge with remaining time), destination, remaining stops, completed stops, assigned route, traffic state, incidents, status. No teleporting; edge traversal takes edge time. Define and test the effect of a traffic change on a vehicle already on an edge.

Controls: start, pause, resume, reset, speed, single step, incident create/resolve, closure/reopen, traffic-cost change, replan. Replanning preserves positions, completed stops, and the clock, and replans only the remaining journey.

Built-in deterministic scenarios (synthetic, labeled as such): Urban Grid, Congested City, Incident Response. About 20-40 nodes and 8-15 customers initially.

## 5. Background jobs
Queue (decision D1, see STATUS.md): a Postgres-backed queue, not Celery + Redis. The API inserts the run as `QUEUED` in one transaction; a SEPARATE worker process claims jobs with `SELECT ... FOR UPDATE SKIP LOCKED`, sets `RUNNING`, and heartbeats. This replaces the outbox (the run row is the queue entry, so DB and queue cannot diverge). All access goes through a small `JobQueue` interface (enqueue, claim, heartbeat, complete, fail, request_cancel) so Celery + Redis can be added later without touching optimizers or API. Cancellation: API sets `CANCELLING` in the DB; the optimizer's cancel signal reads that flag cooperatively. SSE streams from `run_events`. Stale-heartbeat jobs are failed or retried (bounded) by explicit recovery logic.
States: QUEUED, RUNNING, CANCELLING, CANCELLED, COMPLETED, FAILED. Persist the run before acknowledging submission. Support submit, status, SSE progress, cancel, result, failure details, history, bounded retry, and explicit handling of worker interruption. Progress carries real fields (iteration, best objective, feasibility, elapsed, last event). No invented percentages. Cancellation is cooperative and checked in loops. Terminal states are never overwritten by late events. Idempotent run creation, duplicate-result protection, documented retry semantics, explicit transaction boundary (enqueue = insert of the QUEUED row; no outbox needed). No claim of exactly-once execution. Integration tests: queue failure, cancellation race, worker exception, terminal transitions. The database is the only durable record.

## 6. API and database
Prefix `/api/v1`. Pydantic schemas, consistent error shape, sensible status codes, limits on expensive requests, no long jobs inside a request handler, OpenAPI from the real app.
- Health/readiness with dependency status; safe app and algorithm metadata.
- Scenarios: list, create, get, update metadata, create immutable version, get version, delete where permitted.
- Runs: submit, status, SSE, cancel, result, list with filter and pagination.
- Experiments: launch suite, list, detail, comparison data, CSV/JSON export.
- Simulation: create/load session, control, authoritative state, incidents, replan.

Tables: scenarios, scenario_versions, optimization_runs, run_results, run_events (bounded), benchmark_suites. Relational columns for ids, status, timestamps, FKs; JSONB only for variable config and metrics. Indexes, constraints, Alembic migrations from a clean DB (no `create_all` in production). Do not persist every simulation frame.

Configurable limits: scenario size, customers, vehicles, population, iterations, concurrent jobs, benchmark repetitions, export size, event retention. CORS configured. No secrets or stack traces in responses. Ownership boundaries that let auth be added later without touching domain code.

## 7. Testing
- Python unit: graph, closures, Dijkstra, A* vs Dijkstra, route reconstruction, coverage, capacity, depot rules, unreachable, shared evaluator, SA feasibility, QPSO decode/update/repair, seeded determinism, cancellation, simulation transitions, edge traversal, incidents, replanning keeps completed work.
- Backend integration: versioning, persistence, API validation, submission, worker progress, SSE, cancel races, worker failure, results, export, simulation control. Isolated data.
- Frontend: scenario load, graph select/edit, algorithm config, submit/cancel, progress from real API responses, result inspection, sim controls, incidents, theme switch, empty/error states, keyboard access.
- E2E (Playwright): (1) load built-in, run, inspect; (2) edit, save version, run on it; (3) start, observe progress, cancel, verify terminal state; (4) compare runs; (5) advance sim, add incident, verify replanning; (6) export and verify against stored result.

## 8. Frontend workspaces
Shell with top bar, left controls, central React Flow network, right inspector, bottom panel (playback, progress, logs, convergence).
- Command Center: load scenario, view/edit network, inspect items, configure fleet/demand, pick algorithm, launch run, live progress, best solution, current vs optimized, sim controls, incidents, replan, route costs.
- Algorithm Lab: algorithm, params with accurate descriptions, seed, budget, feasibility info, submit/cancel, best-so-far, convergence chart, stats, diagnostics. Never show unsupported settings.
- Scenario Studio: create/edit nodes and directed edges, costs, closures, depots, customers, demands, fleet, validate connectivity and feasibility, save immutable version.
- Experiment Explorer: history with filters, side-by-side comparison, statistics, convergence, reproducibility metadata, seed-level inspection, CSV/JSON export, labels for proven optimum vs reference heuristic.
Shared: TanStack Query for server state, Zustand for workspace state, loading/empty/error/cancelled/completed states, jobs survive navigation and refresh, optimistic UI only where safe, accessible labels and keyboard support, reduced motion, memoized React Flow nodes/edges.

## 9. Documentation and repo quality
Docs written during the build and kept truthful: README, architecture, mathematical_model, algorithms, benchmark_methodology, simulation, api_contracts, interview_guide. Never document unimplemented features as done.
Repo: `.env.example`, Docker Compose, migrations, lockfiles, lint config, test commands, health checks, startup logs, GitHub Actions, a README a fresh developer can follow.

## 10. Definition of done
Everything works from the documented setup: migrations from clean DB; built-in scenarios load; editing and validation work; Dijkstra/A* tested; OR-Tools and SA evaluated by the shared evaluator; QPSO implements its documented update; runs go through the worker with real progress, cancellation, failure handling; results persist across refresh; simulation follows backend state; incidents change costs or availability; replanning preserves positions and completed stops; benchmarks and exports use stored results; tests, lint, and production build pass; no fabricated metrics; docs match behavior; remaining limitations recorded honestly.
