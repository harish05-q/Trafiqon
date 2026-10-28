# Interview guide

Short answers to questions this project invites. Each answer points at the code or the decision
(Dn in STATUS.md) behind it. Numbers quoted are measurements recorded in STATUS.md, on small
synthetic fixtures.

## Architecture
**Why a modular monolith with a separate worker, not microservices?**
- One deployable API, one worker image, and one database is enough for the workload.
- Optimization must not block HTTP handlers, hence the worker process.
- The domain, routing, optimization and simulation packages import no web or database code. A unit test enforces this (`test_import_boundaries.py`), so they stay independently testable.

**Why a PostgreSQL job queue instead of Celery + Redis? (D1)**
- The run row *is* the queue entry. Enqueueing is one INSERT in the API transaction, so the database and the queue cannot disagree, and no outbox is needed.
- Workers claim with `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1)`. A test with 8 threads and 40 runs shows each run is claimed exactly once.
- The cost is polling latency (0.5 s), and Celery is the more commonly expected stack.
- The `JobQueue` interface would accept a Celery implementation later.

**How do you guarantee a cancelled run never becomes COMPLETED?**
- Every transition is a conditional `UPDATE … WHERE status IN (…) AND worker_id = :me`.
- `complete()` writes the status and inserts the result in one transaction. If the run was `CANCELLING`, it ends `CANCELLED`.
- Late heartbeats, progress reports and completions from a worker that lost ownership are no-ops.
- `run_results` has one row per run (the primary key), so a duplicate result is impossible.
- Integration tests cover the claim-versus-cancel race (30 rounds), a stale worker coming back, and delayed completion.

**Exactly-once execution?**
- No; delivery is at least once. A stalled worker's run can be re-queued (bounded by `max_attempts`) while the stalled worker is still running.
- Ownership checks make the stale worker's writes no-ops, so only one result is stored. Execution can still happen twice.

**Why SSE and not WebSockets?**
- Progress only flows from server to client.
- SSE resumes after a reconnect via `Last-Event-ID`, and events come straight from `run_events`.
- One real bug was found here: reading events *before* the status could end a stream before its final events. The fix reads the status first (D18), and the test now passes 5 of 5 reruns.

## Algorithms
**What exactly is the objective?** The sum of `current_time` over every traversed edge of every
route, computed by one evaluator (`routing/evaluation.py`). Distance is reported separately. If a
leg is unreachable, the objective is `None` and the solution is infeasible, never given a
big-M cost.

**Why must the A\* heuristic be admissible, and how is that shown?**
- The heuristic is `h(n) = euclid(n, t) / v_max`, where `v_max` is the largest straight-line length per minute over the open edges. The triangle inequality then gives admissibility and consistency.
- If any node lacks coordinates, or an open edge has zero time but positive length, it falls back to `h = 0`.
- Tests check that A\* equals Dijkstra on every node pair of every fixture and on 400 random graphs.

**How does OR-Tools handle one-way streets and unreachable pairs?**
- It uses a directed shortest-path cost matrix.
- Unreachable arcs are *removed* from the solver's next-node domains, so no large penalty cost is used.
- Vehicles that may end at several depots use per-vehicle dummy end nodes.
- A result is labelled proven optimal only on `ROUTING_OPTIMAL`, which never happens with a time-limited guided local search.

**Is the QPSO hybrid "real QPSO"?**
- The *update rule* is the standard QPSO one: a mean-best attractor and the `p ± β|mbest−x|ln(1/u)` step, with β falling linearly. It is applied to continuous random keys.
- Everything else is a discrete, problem-specific layer: decoding, repair, local search and write-back. Hence "QPSO-inspired hybrid".
- Tests verify the update's statistics (E|x'−p| = β·L) and that decoding is exactly invertible.

**Does the QPSO update actually matter?**
- An ablation replaces it with uniform resampling at equal particle budgets. With local search off, mean gaps were 1.17 % vs 5.42 % (Congested City) and 23.6 % vs 30.9 % (30-customer grid).
- With local search on, the local search does most of the work: 0.04 % vs 0.59 % on the grid, and a tie on Congested City.
- With n = 5 seeds and no significance test, this is evidence the update is not inert, not a performance claim.

**Which is best?**
- On these small fixtures all three reach the same best observed values (73.8 / 60.792 / 55.153 min) in most seeds.
- SA is the fastest by wall time.
- On the 30-customer grid, QPSO with local search took about 5 s, against SA's 0.2 s, for a similar objective.
- Budgets use different units (time, moves, particle updates), so compare objective together with wall time (D12).

**Complexity, roughly?**
- Dijkstra: O((V+E) log V).
- Cost matrix: L single-source runs for L depot and customer locations.
- SA move: O(route length) to re-cost the affected routes.
- QPSO: O(M·T·(decode + repair + LS)). Local search dominates, at O(n²) re-costing per pass.
- Exact replan: k! permutations for k ≤ 7 stops per vehicle.

## Simulation
**What happens if traffic changes while a vehicle is on the road? (D28)** Position is
progress in [0, 1]. The vehicle keeps its progress, and the remainder `(1−p)·current_time` is
re-timed. A closure lets it finish the road it is on, but blocks entry.

**How is real-time playback deterministic? (D30)**
- Wall time is converted into *whole ticks*, with the remainder carried, so the engine only ever sees whole ticks.
- The state is a function of the tick at which each command was applied.
- Tests show identical scripts give identical states, and that results are the same at any tick size from 0.1 to 3 minutes.

**What does replanning preserve, and what does it not do? (D29)**
- It preserves the clock, positions, the edge in progress and completed stops.
- It reorders each vehicle's *own* remaining stops; goods are on board, so customers are never moved between vehicles.
- Unreachable stops are reported as unserved. A vehicle that cannot reach its depot is reported as stranded, and the simulation never claims to be finished while one is.

## Failure modes and limitations
- **Simulation sessions:** in-memory, single API process, lost on restart (D27).
- **Benchmarks:** fixtures are small; gaps are against the best observed heuristic; no lower bounds.
- **SSE and the queue:** both poll the database, which is fine for one node.
- **Authentication:** none yet; `owner_id` columns mark where it will plug in.
- **Spec tokens:** the spec's light accent `#D94F35` cannot carry AA small text, so a darker fill is used for buttons (D19).

## Testing strategy
- **Pure core:** exhaustive unit tests, including NetworkX cross-checks, property tests and statistical checks of the QPSO update.
- **Integration:** run on *real* PostgreSQL. SKIP LOCKED cannot be tested on SQLite.
- **End-to-end (Playwright):** run against the real API, a separate worker and a production build. Workflows 1–6 cover running, editing, cancelling, comparing, simulating with incidents and replanning, and export-versus-stored-result.
- **Accessibility:** axe-core WCAG 2 A/AA scans of every workspace.
- **Real bugs these tests found** (all fixed): a one-tick-late stop completion, an SSE stream ending early, an inspector showing original rather than simulated road state, and a stranded-vehicle replan raising instead of reporting.
