# TRAFIQON — Master Engineering, Research, and Product Build Specification

## 1. Your Role and Mission

Act as a principal software architect, senior full-stack engineer, optimization researcher, simulation engineer, and product designer.

Your mission is to design, implement, test, document, and verify **TRAFIQON**, an interactive transportation optimization and simulation workbench.

TRAFIQON explores how classical graph algorithms, operations research, metaheuristic optimization, and quantum-inspired search techniques can improve vehicle-routing decisions in dynamic transportation networks.

This must be a genuine, working engineering and research application—not a static dashboard, UI prototype, CRUD application, or collection of decorative charts.

The final product must demonstrate:

- Correct graph algorithms and constraint-aware vehicle routing.
- A technically defensible hybrid QPSO-inspired discrete optimizer.
- Fair and reproducible algorithm comparisons.
- Dynamic traffic conditions, incidents, and route replanning.
- Reliable asynchronous optimization jobs with real progress and cancellation.
- Persistent scenarios, experiment results, and execution history.
- A polished, interactive transportation research interface.
- A test suite and documentation sufficient for another engineer to understand and reproduce the results.

Prioritize correctness, technical depth, reliability, usability, and reproducibility over feature count.

## 2. Non-Negotiable Operating Rules

1. Inspect the existing repository, environment, available dependencies, and project state before modifying anything.
2. Preserve useful existing work. Do not overwrite or discard files without understanding their purpose.
3. Use the strongest practical implementation choices that fit the architecture and project constraints.
4. Do not fabricate benchmark measurements, test results, system activity, simulation events, or optimization progress.
5. Do not substitute a placeholder, random route generator, or generic metaheuristic for a required algorithm.
6. Do not claim that a quantum-inspired algorithm executes on quantum hardware or provides a quantum speedup.
7. Do not declare a feature complete until its implementation and relevant tests have been inspected.
8. Do not leave core interactions connected only to mock data, hardcoded arrays, or frontend-only state.
9. Do not create unnecessary microservices, Kubernetes infrastructure, distributed systems complexity, or paid-service dependencies.
10. Prefer a working, tested vertical slice over implementing numerous disconnected screens.
11. If an algorithmic or architectural requirement is infeasible or ambiguous, explain the issue, recommend a defensible solution, and document the decision.
12. Never silently weaken a requirement to make a demo appear complete.

Use AI coding assistance and parallel agents where useful, but review their changes, run the tests, and resolve integration conflicts yourself.

## 3. Product Identity and Scope

**Product name:** TRAFIQON

**Product category:** Transportation optimization, routing simulation, and computational research workbench.

**Product positioning:** An engineering platform for experimenting with route optimization under vehicle-capacity constraints, changing road costs, and traffic incidents.

**Primary users:**
- Software engineers and algorithm researchers.
- Transportation and operations-research students.
- Engineers comparing routing and optimization methods.
- Interviewers evaluating algorithmic depth and engineering quality.

The application should allow a user to:

1. Explore and modify a transportation network.
2. Configure a routing scenario with depots, customers, vehicles, demands, capacities, and road conditions.
3. Select a routing or optimization algorithm.
4. Execute optimization asynchronously.
5. Inspect candidate routes, objective values, feasibility, and convergence.
6. Compare algorithms under controlled experimental conditions.
7. Simulate vehicle movement and changing traffic conditions.
8. Introduce incidents and observe route replanning.
9. Save scenarios, runs, and experimental results.
10. Export reproducible experiment data and review the methodology.

The initial problem domain is a **directed, capacity-constrained vehicle-routing problem (CVRP) over a transportation graph**, with dynamic edge travel costs and incident-driven replanning.

Do not present the initial implementation as a universal solution to traffic-signal control, traffic assignment, fleet dispatch, or all transportation optimization problems.

## 4. Architecture and Technology Choices

Use a modular monolith with a separately running background worker.

### Frontend

- Next.js App Router.
- React and strict TypeScript.
- Tailwind CSS.
- shadcn/ui components, customized to the TRAFIQON design system.
- React Flow for the editable road-network graph.
- Zustand for focused client-side simulation and workspace state.
- TanStack Query for server-state fetching, caching, invalidation, and mutations.
- Apache ECharts for analytical visualizations.
- Vitest and React Testing Library.
- Playwright for end-to-end workflows.

Use stable, compatible package versions and commit the lockfile. Avoid unnecessary libraries that duplicate existing capabilities.

### Backend

- Python.
- FastAPI.
- Pydantic for request and response validation.
- SQLAlchemy 2.x.
- Alembic migrations.
- NumPy for numerical computation.
- NetworkX where appropriate for graph representation and validation.
- OR-Tools for the classical CVRP reference implementation.
- Pytest for testing.

Keep the core graph model, objective evaluator, constraints, and optimization algorithms independently testable and usable without HTTP requests or a database.

### Background processing

> **Recorded deviation (STATUS.md D1):** the Celery + Redis requirement below is deferred. The implementation uses a Postgres-backed queue with a separate worker process behind a `JobQueue` interface. All other requirements in this section still apply.

- Celery for asynchronous optimization and benchmark tasks.
- Redis as the Celery broker and supporting coordination service.
- PostgreSQL for durable application and job-result persistence.
- Server-Sent Events (SSE) for streaming run progress to the frontend.

Redis must not be the only durable record of an optimization run.

### Database

- PostgreSQL with SQLAlchemy and Alembic.
- JSONB for genuinely variable algorithm configuration, metrics, and structured metadata.
- Explicit relational fields for important identifiers, statuses, timestamps, and relationships.

### Development and delivery

- Docker Compose for the local application stack.
- npm for frontend package management.
- uv for Python environment and dependency management.
- Ruff for Python linting and formatting.
- ESLint and Prettier for frontend code.
- GitHub Actions for automated linting, testing, and relevant build checks.

Use environment variables for configuration and provide a complete `.env.example`.

Do not commit secrets or require paid APIs for core functionality.

## 5. Required System Architecture

Separate the application into clear modules:

- `web`: frontend and interactive workspace.
- `api`: HTTP API, validation, authentication-ready boundaries, and orchestration.
- `domain`: graph entities, routing constraints, objectives, and shared types.
- `routing`: shortest-path algorithms and route evaluation.
- `optimization`: classical baselines and the hybrid QPSO-inspired optimizer.
- `simulation`: deterministic discrete-time vehicle and incident simulation.
- `experiments`: benchmark execution, statistics, and export.
- `worker`: Celery tasks, progress reporting, cancellation, and recovery.
- `persistence`: database models, repositories, and migrations.

Adapt the physical directory structure to the existing repository, but maintain these logical boundaries.

The optimizer must not depend on React, FastAPI request objects, database sessions, or frontend-specific data structures.

The simulation must not rely on frontend animation frames as its authoritative state.

The frontend must obtain persisted scenarios, optimization results, and authoritative simulation state from the backend.

Document significant architectural decisions and their trade-offs.

## 6. Mathematical and Domain Model

Represent the transportation network as a directed graph:

G = (V, E)

Where:

- V represents intersections or routing nodes.
- E represents directed road segments.
- Each edge has a travel cost and relevant traffic metadata.
- Edge directionality and availability must be respected.

A road segment should support relevant fields such as:

- Unique identifier.
- Source and destination node identifiers.
- Distance.
- Base travel time.
- Current travel time.
- Capacity or congestion metadata where applicable.
- Availability or closure status.
- Optional road classification.

A routing scenario contains:

- A directed transportation graph.
- One or more depots.
- Customer or destination nodes.
- Demand at each customer.
- A fleet of vehicles.
- Vehicle capacity constraints.
- Algorithm configuration.
- Traffic and incident settings.

For the initial CVRP, define a route for each vehicle that begins and ends at a valid depot and serves its assigned customers.

The objective is to minimize the sum of travel costs over all vehicle routes.

For a valid solution S:

f(S) = sum of the travel costs of all traversed route edges.

If shortest-path distances between customers are used to formulate CVRP, explicitly construct the directed cost matrix using the current network conditions. Document how the edge-level paths are reconstructed for visualization.

The following constraints must be validated:

- Every required customer is served exactly once.
- Vehicle demand does not exceed vehicle capacity.
- Every vehicle route begins and ends at an allowed depot.
- Every traversed edge exists and is currently traversable.
- Every required route leg is reachable.
- Invalid, closed, or disconnected edges cannot silently become feasible routes.

For unreachable customer pairs, report infeasibility or apply an explicitly documented policy. Never substitute an arbitrary large cost and then present the result as a valid route without explanation.

The initial primary objective is total travel time.

Track route distance, feasibility, and route disruption separately. If a route-stability penalty is introduced later, make it an explicit configurable objective component and report the original travel-time objective independently.

Use a single authoritative objective evaluator for all algorithms.

All objective values shown in the interface must correspond to the same documented cost definition and the same scenario version.

## 7. Required Algorithms

### 7.1 Dijkstra

Implement and test Dijkstra's algorithm for shortest paths with nonnegative edge weights.

Respect directed edges and closures.

### 7.2 A*

Implement A* with an admissible heuristic for the chosen graph representation.

If geographic coordinates are used, explain when the heuristic is valid. Fall back to a zero heuristic when a safe admissible heuristic cannot be established.

Test A* against Dijkstra on appropriate graphs and verify equal optimal costs where both are applicable.

### 7.3 Classical CVRP reference

Use OR-Tools to implement a capacity-constrained vehicle-routing baseline.

- Configure valid customer demands and vehicle capacities.
- Handle unreachable paths and infeasible scenarios explicitly.
- Configure stopping criteria and search limits.
- Return valid routes, objective values, solver status, and execution metadata.
- Never claim that a time-limited heuristic solver has proven global optimality.

For small instances, optionally use an exact method to establish a proven optimum. Clearly record whether optimality was actually proven.

### 7.4 Simulated Annealing baseline

Implement a genuine Simulated Annealing baseline using documented neighborhood moves, acceptance criteria, a temperature schedule, and stopping conditions.

Use the same solution representation, feasibility rules, and objective evaluator as the research optimizer wherever practical.

### 7.5 Hybrid QPSO-inspired discrete optimizer

Implement a research-oriented, hybrid QPSO-inspired discrete optimization method. It must be a real, separately testable algorithm, not a renamed random search.

Before implementing it, write down the representation and update mechanism mathematically.

The implementation must document:

1. The candidate-solution encoding.
2. The decoding from encoded candidates to customer orders and vehicle routes.
3. How feasible vehicle assignments are constructed or repaired.
4. The personal-best or candidate-best information retained.
5. The population or neighborhood-best information retained.
6. The quantum-inspired update rule and the role of its parameters.
7. Any local-attractor or contraction-expansion concepts actually implemented.
8. The discrete operators used to modify route solutions.
9. The treatment of infeasible solutions.
10. The termination conditions and computational budget.

A suitable candidate design may use random-key encoding for customer ordering or assignment, followed by deterministic decoding and a feasibility-aware route constructor. Choose the representation that best supports correctness and clear mathematical explanation.

If the implementation uses a QPSO-inspired update in continuous latent space, define the mapping from latent candidates to valid discrete routing solutions precisely. If the update instead operates on a discrete representation, document the actual discrete adaptation and explain which QPSO concepts are retained.

Possible discrete neighborhood operators include:

- Relocate a customer.
- Swap two customers.
- Reverse a route subsequence where directionality and feasibility permit.
- Reassign a customer between vehicle routes.
- Reconstruct a route using a feasible insertion procedure.

Operators must preserve or explicitly repair route feasibility.

Use a deterministic random-number generator with a user-supplied seed.

Retain the best feasible incumbent. Track objective evaluations, iteration history, best-so-far cost, feasibility, and elapsed time.

Provide a configurable stopping budget and cooperative cancellation checks.

Make the optimizer reproducible under identical inputs, configuration, seed, and software version, subject to any documented nondeterministic dependencies.

Do not claim that the method is mathematically equivalent to canonical QPSO unless it genuinely implements the relevant formulation.

If the intended update rule cannot be implemented and justified, stop and document the unresolved issue rather than silently substituting a generic metaheuristic.

### 7.6 Common algorithm interface

All optimization algorithms must use a shared contract with:

- Algorithm identifier and version.
- Validated input scenario.
- Algorithm configuration.
- Random seed where applicable.
- Progress callback.
- Cancellation signal.
- Best feasible solution when available.
- Objective value and feasibility status.
- Iteration or evaluation history.
- Execution time and termination reason.
- Structured diagnostic metadata.

Separate the solution evaluator from the optimizer so every method is assessed consistently.

## 8. Benchmarking and Scientific Integrity

Build a reproducible benchmarking framework.

Compare the algorithms on identical scenario versions and comparable computational budgets. When equal budgets are inappropriate, explicitly explain the difference.

Record at least:

- Objective value.
- Feasibility status.
- Feasibility rate across repeated runs.
- Wall-clock execution time.
- Time to first feasible solution.
- Number of objective evaluations.
- Iteration history and convergence.
- Replanning latency.
- Route disruption after incidents.
- Variation across random seeds.
- Optimality gap only when a valid reference optimum or lower bound is available.

Define the optimality-gap calculation precisely and distinguish a proven optimum from a heuristic reference solution.

For repeated stochastic experiments, report sample count and appropriate summary statistics, such as mean, median, standard deviation, and best observed result.

Use explicit seeds and preserve scenario versions, algorithm versions, configuration, and run metadata.

Create deterministic benchmark fixtures suitable for automated tests. Clearly label small synthetic fixtures and larger experimental scenarios.

Provide exportable CSV and JSON results with enough metadata to reproduce an experiment.

Do not fabricate results to make one algorithm appear superior. The interface must display measured results only, and clearly distinguish measured, derived, estimated, and simulated quantities.

## 9. Dynamic Transportation Simulation

Implement a deterministic, discrete-time simulation engine.

The simulation must track:

- Simulation time and tick duration.
- Vehicle identifier and current position.
- Current edge or node.
- Remaining travel time on an active edge.
- Destination and remaining stops.
- Assigned route.
- Completed stops.
- Current traffic conditions.
- Incidents and affected roads.
- Current simulation status.

A vehicle traversing an edge must respect the edge's travel time. It must not jump directly between arbitrary nodes or teleport when its route changes.

Represent in-progress edge traversal explicitly. Define and test how traffic changes affect a vehicle already traversing an edge.

The engine must support:

- Start.
- Pause.
- Resume.
- Reset.
- Configurable simulation speed.
- Step-by-step advancement for debugging.
- Incident creation and resolution.
- Road closure and reopening.
- Traffic-cost changes.
- Route replanning.

When replanning, preserve current vehicle positions, completed stops, and valid route progress. Replan only the remaining portion of a vehicle's journey.

Do not silently discard completed work or reset the simulation clock during replanning.

Provide three deterministic built-in scenarios:

1. Urban Grid.
2. Congested City.
3. Incident Response.

Start with modest graph sizes, approximately 20–40 intersections and 8–15 customers, and scale only after profiling. These are initial targets, not mandatory limits.

The simulation engine must be independently testable without the frontend.

The backend is authoritative for simulation state and vehicle progress. The frontend may interpolate between authoritative updates for smooth rendering, but it must not invent state transitions.

## 10. Background Jobs, Progress, and Cancellation

Implement durable optimization-run lifecycle management.

Required run states:

- QUEUED
- RUNNING
- CANCELLING
- CANCELLED
- COMPLETED
- FAILED

Persist the run record before reporting successful job acceptance.

Use stable identifiers for runs and explicit ownership and association with the scenario version, algorithm, and configuration.

Support:

- Job submission.
- Run-status retrieval.
- Progress streaming through SSE.
- Cancellation requests.
- Result retrieval.
- Failure details.
- Run history.
- Bounded retry behavior where safe.
- Recovery or explicit failure handling after worker interruption.

Progress updates should contain meaningful fields such as current iteration, best objective, feasible-solution status, elapsed time, and the most recent event.

Do not invent percentage completion when the algorithm cannot calculate a meaningful percentage. Where total work is known, calculate progress from real execution state.

Cancellation must be cooperative and checked within optimization loops and other long-running operations.

A cancelled run must not later overwrite its terminal status with COMPLETED because of a delayed progress event.

Make run creation idempotent where appropriate, protect against duplicate result persistence, and document retry semantics.

Use a well-defined transaction boundary between database state, queue submission, and worker execution. Consider a transactional outbox or another justified mechanism if required for reliable dispatch.

Do not claim guaranteed exactly-once execution if the chosen infrastructure cannot provide it.

Add integration tests for queue failures, cancellation races, worker exceptions, and terminal-state transitions.

## 11. Backend API

Prefix application routes with `/api/v1`.

Provide a documented REST API covering the following capabilities.

### Health and configuration

- Health and readiness checks.
- Relevant service-dependency status.
- Safe application and algorithm metadata.

### Scenarios

- List scenarios.
- Create a scenario.
- Retrieve a scenario.
- Update scenario metadata or configuration.
- Create an immutable scenario version.
- Retrieve a specific version.
- Delete a scenario where permitted.

Do not silently mutate a scenario version already referenced by a completed experiment.

### Optimization runs

- Submit an optimization run.
- Retrieve run status.
- Stream progress through SSE.
- Request cancellation.
- Retrieve a completed result.
- List runs with useful filtering and pagination.

### Experiments and benchmarks

- Create or launch a benchmark suite.
- List experiments.
- Retrieve experiment details.
- Retrieve comparison data.
- Export supported results as CSV and JSON.

### Simulation

Provide the API operations needed to create or load a simulation session, advance or control it, retrieve authoritative state, introduce or resolve incidents, and request route replanning.

Use Pydantic request and response schemas. Validate all input at the API boundary.

Provide consistent error responses, sensible HTTP status codes, timeouts, and limits for expensive requests.

Do not execute long optimization jobs synchronously inside an HTTP request handler.

Generate OpenAPI documentation from the actual FastAPI implementation.

## 12. Database Design

Use SQLAlchemy models and Alembic migrations.

Implement the following core entities, adjusting relationships and fields when technically justified.

### scenarios

Stores scenario identity, metadata, creation time, and current version reference.

### scenario_versions

Stores immutable, versioned graph topology, demands, fleet configuration, traffic settings, and relevant scenario metadata.

### optimization_runs

Stores run identity, scenario-version reference, algorithm identifier and version, configuration, seed, lifecycle status, timestamps, progress summary, and termination information.

### run_results

Stores the best feasible solution when available, objective values, feasibility information, route details, evaluation counts, convergence summaries, and relevant metrics.

### run_events

Stores meaningful progress and lifecycle events with timestamps and structured payloads. Avoid unbounded event volume.

### benchmark_suites

Stores benchmark configuration, scenario selection, algorithm configuration, repetition count, random seeds, budget policy, and aggregate experiment metadata.

Add indexes for common lookups, foreign-key constraints, appropriate uniqueness constraints, and explicit transaction boundaries.

Keep large, rapidly changing progress streams manageable. Do not write every simulation frame to the database unless there is a clear need.

Provide migrations from a clean database. Do not rely on `create_all()` as the production schema migration strategy.

## 13. Visual Design System

### 13.1 Design philosophy

Use a sophisticated **industrial-cartography aesthetic** combining a transportation command center with the precision of scientific research software.

TRAFIQON should feel like professional transportation engineering software: technical, purposeful, data-dense, visually distinctive, and scientifically credible.

Draw inspiration from:

- Traffic-control and transport operations systems.
- Scientific cartography.
- Industrial instrumentation.
- Computational research software.
- Engineering workstations.

Avoid generic AI/SaaS dashboard styling, excessive neon, blue-purple gradient themes, decorative glassmorphism, oversized glowing typography, unnecessary cards, and ornamental animations.

Every visual element must serve a functional purpose.

Prioritize the road network, route quality, congestion patterns, incidents, vehicle positions, simulation state, algorithm performance, and experimental results.

### 13.2 Dark theme tokens

Use these exact initial design tokens:

| Token | Value |
|---|---|
| Application background | `#111210` |
| Primary surface | `#191B17` |
| Secondary surface | `#20221E` |
| Elevated surface | `#292B25` |
| Primary text | `#E9E5DA` |
| Secondary text | `#A5A397` |
| Muted text | `#77786F` |
| Borders and dividers | `#363830` |
| Primary accent — Signal Orange | `#FF6B35` |
| Secondary accent — Vermilion | `#D94F35` |
| Analytical highlight — Ochre | `#B78B48` |
| Secondary data — Sage | `#727C67` |
| Normal traffic / healthy state | `#78A083` |
| Congestion warning | `#D9B45B` |
| Critical incident / road closure | `#D94F35` |
| Selected route / primary interaction | `#FF6B35` |
| Disabled / inactive | `#77786F` |

Signal orange is the principal interaction and route-selection color. Vermilion denotes critical states and incidents. Ochre denotes congestion and analytical emphasis. Sage denotes healthy states and secondary data.

Do not use these colors merely as decoration.

Pair critical status colors with labels, icons, line patterns, or other non-color indicators.

Validate text contrast and ensure disabled elements remain understandable.

### 13.3 Light analytical theme tokens

Provide a coordinated warm-paper theme for research reports, experiment analysis, long-form methodology, documentation, and export-oriented views.

| Token | Value |
|---|---|
| Application background | `#F3F0E8` |
| Primary surface | `#FAF8F2` |
| Secondary surface | `#E9E4D8` |
| Primary text | `#252722` |
| Secondary text | `#65665D` |
| Borders and dividers | `#D5D0C3` |
| Primary accent | `#D94F35` |
| Secondary accent | `#727C67` |

Keep the light theme visually consistent with the dark command center.

The main simulation and command-center workspace must start in dark mode. Use the light theme where it improves reading and analytical presentation.

Do not randomly mix light and dark surfaces within a single workspace.

Theme switching must update all relevant application components through centralized tokens.

### 13.4 Typography

Use:

- **Inter** for interface typography, navigation, headings, labels, and explanatory content.
- **JetBrains Mono** for numerical readouts, algorithm parameters, execution times, objective values, iterations, network statistics, run IDs, and technical metadata.

Typography must be compact and legible.

Establish hierarchy through size, spacing, weight, and contrast rather than oversized text, decorative weights, or universal all-caps labels.

Use tabular numerals for comparable numeric measurements where appropriate.

### 13.5 Workspace layout

Use a persistent, workspace-oriented navigation shell.

The desktop command center must contain:

**Top bar**
- TRAFIQON identity.
- Workspace navigation.
- Current scenario.
- Connection or service status.
- Simulation state.
- Essential global controls.

**Left control panel**
- Scenario configuration.
- Network and traffic settings.
- Depot, customer, and fleet configuration.
- Algorithm selection and parameters.
- Incident controls.

**Central workspace**
- The road network as the dominant visual element.
- Vehicles and their positions.
- Primary and alternative routes.
- Congestion and closed-road overlays.
- Contextual network editing.

**Right inspector**
- Selected node, edge, vehicle, route, or algorithm run.
- Relevant editable properties.
- Current travel cost and traffic status.
- Route and vehicle diagnostics.

**Bottom panel**
- Simulation playback and time controls.
- Optimization progress.
- Execution logs and event history.
- Convergence summaries.
- Experiment and run details.

Allow panels to collapse or resize where useful. Avoid unnecessary nested cards, excessive empty space, and heavy shadows.

Adapt the layout to smaller screens with responsive panels and touch-accessible controls. Preserve access to essential actions and prevent inspectors from permanently obscuring the network.

### 13.6 Road-network visualization

The road network is the primary visual focus.

- Ordinary roads: subdued graphite or neutral-gray strokes.
- Selected or best-known optimized route: signal orange.
- Alternative candidate paths: distinguishable, restrained secondary treatments.
- Congested roads: ochre or amber treatments.
- Critical incidents and closed roads: vermilion.
- Healthy traffic: sage green where its meaning is explicitly defined.
- Depots, customers, intersections, and vehicles: consistent, distinguishable markers.

Provide visual distinctions for selected, hovered, active, inactive, and disabled elements.

Use line weight, contrast, dashed patterns, markers, direction arrows, and labels to distinguish overlapping routes. Avoid excessive glow.

Include a readable legend, contextual tooltips, useful edge information, and meaningful node information.

Road selection should expose relevant details, including direction, travel time, distance, traffic status, closure state, and route membership when applicable.

Do not imply that a synthetic graph is geographically accurate. Label synthetic scenarios clearly.

### 13.7 Algorithm and research visualizations

Present quantum-inspired optimization as a serious computational method.

Provide meaningful visualizations for:

- Best objective value over time or iterations.
- Candidate and incumbent solutions where meaningful.
- Objective evaluations.
- Feasibility.
- Execution time.
- Convergence history.
- Route costs and route changes.
- Comparative benchmark performance.
- Seed-to-seed variation.
- Replanning latency.

Use consistent visual encoding across algorithm runs.

Traffic-semantic colors must not be confused with algorithm-series colors. Define a separate, restrained series palette for experiment comparisons and provide explicit legends.

Use charts, compact statistics, and tables where they best support interpretation.

Label axes, units, sample counts, and measurement definitions.

Clearly distinguish measured results, derived statistics, estimated quantities, and simulation outputs.

Do not fabricate live activity or independently animate convergence.

### 13.8 Motion and interaction

Use restrained, purposeful transitions for:

- Road and node selection.
- Route highlighting.
- Incident creation and resolution.
- Vehicle movement.
- Best-solution updates.
- Algorithm selection.
- Experiment selection.
- Panel expansion and contextual inspection.

Vehicle movement must follow authoritative simulation state and simulation time.

Optimization progress and convergence must reflect actual execution.

Avoid particle effects, looping background animations, excessive glow, and decorative motion without functional meaning.

Support keyboard navigation, visible focus indicators, adequate contrast, and reduced-motion preferences.

The application must remain fully understandable and functional with animations disabled.

### 13.9 Design implementation rules

Create centralized design tokens for recurring colors, typography, spacing, radii, borders, and elevations.

Use consistent spacing, iconography, panel boundaries, and component behavior.

Use signal orange selectively. Preserve neutral surfaces and readable typography as the visual foundation.

Do not introduce arbitrary accent colors or replace specified tokens without a documented functional reason.

Implement the design system in reusable components and theme variables rather than scattered hardcoded styles.

## 14. Frontend Workspaces

### 14.1 Command Center

Build the main operational workspace.

It must support:

- Loading built-in or saved scenarios.
- Viewing and editing the network.
- Inspecting roads, nodes, vehicles, depots, and customers.
- Configuring fleet and demand constraints.
- Selecting algorithms and parameters.
- Launching an optimization run.
- Viewing real-time job progress.
- Inspecting the best available feasible solution.
- Comparing the current and optimized routes.
- Starting, pausing, resuming, stepping, and resetting simulation.
- Creating and resolving incidents.
- Requesting route replanning.
- Inspecting route costs and execution details.

All major actions must work against actual application logic.

### 14.2 Algorithm Lab

Provide a focused workspace for algorithm configuration and comparison.

Include:

- Algorithm selection.
- Parameter configuration.
- Random seed.
- Stopping budget.
- Constraint and feasibility information.
- Run submission and cancellation.
- Best-so-far objective.
- Convergence chart.
- Execution statistics.
- Algorithm-specific diagnostics.

Explain parameters through concise, technically accurate descriptions.

Never display unsupported algorithm settings or claim that a configuration is active when it is not.

### 14.3 Scenario Studio

Provide an interface to:

- Create a network from scratch.
- Load built-in scenarios.
- Add, edit, and remove nodes and directed edges.
- Configure road costs and closure state.
- Define depots and customers.
- Set customer demands.
- Configure fleet size and vehicle capacities.
- Validate connectivity and scenario feasibility.
- Save a new immutable scenario version.

Use React Flow custom nodes and edges with proper interaction states.

Prevent invalid graph edits or provide clear validation errors.

### 14.4 Experiment Explorer

Provide:

- Run and benchmark history.
- Filtering by scenario, algorithm, date, and status.
- Side-by-side algorithm comparison.
- Objective and runtime statistics.
- Convergence charts.
- Reproducibility metadata.
- Seed-level result inspection.
- CSV and JSON exports.
- Clear labels for proven optima, reference heuristics, and measured outcomes.

The interface must display persisted experimental results, not fabricated examples disguised as live measurements.

### 14.5 Shared frontend requirements

Use TanStack Query for server state and Zustand for focused client-side workspace state.

Implement loading, empty, validation-error, service-error, cancellation, and completion states.

Ensure long-running jobs remain understandable if the user navigates between workspaces or refreshes the page.

Use optimistic UI only where safe and reconcile it with authoritative backend responses.

Provide useful keyboard shortcuts only when discoverable and nonconflicting.

Use accessible labels, semantic HTML, keyboard navigation, and reduced-motion support.

## 15. Performance, Reliability, and Security

Apply appropriate request validation, resource limits, timeouts, and safe error handling.

Do not allow arbitrary unbounded graph sizes, benchmark repetitions, optimizer populations, or execution durations.

Set configurable limits for:

- Scenario size.
- Number of customers and vehicles.
- Optimizer population and iterations.
- Concurrent jobs.
- Benchmark repetitions.
- Result-export size.
- Progress-event retention.

Keep expensive optimization out of the API process.

Avoid unnecessary rerenders of large React Flow graphs. Use memoized custom nodes and edges where appropriate.

Use background execution and bounded concurrency for expensive tasks.

Implement appropriate CORS configuration for local development and production configuration.

Do not expose secrets, internal stack traces, or sensitive configuration through the API.

Design ownership and authorization boundaries so authentication can be added safely without coupling the domain logic to a particular identity provider.

Add basic rate limiting or other justified safeguards for expensive job-submission endpoints if the deployment context requires them.

## 16. Testing Requirements

Testing is a core deliverable.

### Python unit tests

Test:

- Directed graph behavior.
- Edge costs and closure handling.
- Dijkstra correctness.
- A* correctness against Dijkstra.
- Route reconstruction.
- Customer coverage.
- Capacity constraints.
- Depot constraints.
- Unreachable destinations.
- Shared objective evaluation.
- Simulated Annealing feasibility.
- QPSO-inspired update and decoding behavior.
- Feasibility repair.
- Deterministic seeded behavior.
- Cancellation behavior.
- Simulation state transitions.
- Vehicle edge traversal.
- Incident handling.
- Replanning without loss of completed work.

### Backend integration tests

Test:

- Scenario creation and versioning.
- Database persistence.
- API validation and error handling.
- Optimization-job submission.
- Worker progress events.
- SSE event behavior.
- Cancellation and terminal-state races.
- Worker failures and recovery.
- Result persistence and retrieval.
- Experiment export.
- Simulation control operations.

Use isolated test data and a clear strategy for integration tests that require PostgreSQL and Redis.

### Frontend tests

Test:

- Scenario loading.
- Graph selection and editing.
- Algorithm configuration.
- Job submission and cancellation.
- Progress rendering from actual API responses.
- Run-result inspection.
- Simulation controls.
- Incident creation and resolution.
- Theme switching.
- Empty and error states.
- Keyboard-accessible interactions.

### End-to-end tests

At minimum, verify these complete workflows:

1. Load a built-in scenario, run an algorithm, and inspect its result.
2. Create or modify a scenario, save a version, and run optimization against that version.
3. Start a run, observe progress, cancel it, and verify its terminal state.
4. Compare multiple completed algorithm runs.
5. Advance a simulation, introduce an incident, and verify a valid remaining-route replanning workflow.
6. Export an experiment and verify that the exported metadata corresponds to the stored result.

Do not report tests as passing unless they have actually run and passed.

## 17. Documentation

Maintain documentation that reflects the implemented system:

- `README.md`: product overview, setup, run commands, environment configuration, and troubleshooting.
- `docs/architecture.md`: architecture, component boundaries, data flow, and infrastructure decisions.
- `docs/mathematical_model.md`: graph formulation, CVRP definition, objective, constraints, and assumptions.
- `docs/algorithms.md`: algorithm implementations, complexity considerations, QPSO-inspired formulation, encoding, decoding, and limitations.
- `docs/benchmark_methodology.md`: budgets, seeds, scenarios, statistical summaries, reference optima, and reproducibility.
- `docs/simulation.md`: simulation clock, vehicle state, incident handling, and replanning semantics.
- `docs/api_contracts.md`: actual endpoints, schemas, error responses, and SSE events.
- `docs/interview_guide.md`: architecture decisions, algorithmic trade-offs, complexity, failure modes, limitations, and likely technical interview questions.

Include diagrams where they clarify real architecture or data flow.

Do not document unimplemented features as completed.

## 18. Repository Quality and Developer Experience

Provide:

- A complete `.env.example`.
- Docker Compose configuration for the required services.
- Database migrations.
- Dependency lockfiles.
- Lint and formatting configuration.
- Test commands.
- Health checks.
- Useful startup logs.
- Clear service names.
- Reliable local development instructions.
- A GitHub Actions workflow for relevant quality checks.

Ensure a fresh developer can follow the README to install dependencies, start the stack, migrate the database, run tests, and launch the application.

Avoid requiring a paid external API for any core workflow.

If a third-party service is optional, provide a local or deterministic alternative where appropriate.

## 19. Implementation Milestones

Execute the project in the following order. Adjust the sequence only when repository conditions or a documented technical dependency justify doing so.

### Milestone 0 — Inspect and plan

- Inspect the repository, existing implementation, package managers, runtime versions, and environment.
- Identify reusable work and existing defects.
- Confirm the proposed architecture and dependency compatibility.
- Create a milestone plan with explicit acceptance criteria.
- Record assumptions, risks, and technical decisions.
- Do not begin by generating every frontend page.

### Milestone 1 — Domain and routing engine

- Define the graph and scenario models.
- Implement route-cost calculation and constraints.
- Implement Dijkstra and A*.
- Implement route reconstruction and validation.
- Add deterministic fixtures and unit tests.

### Milestone 2 — Classical optimization and evaluation

- Integrate the OR-Tools CVRP baseline.
- Implement Simulated Annealing.
- Establish the common algorithm interface.
- Add objective evaluation and feasibility checks.
- Establish reproducible baseline experiments.

### Milestone 3 — Research optimizer

- Write the QPSO-inspired mathematical formulation.
- Implement candidate encoding, decoding, and feasibility handling.
- Implement the documented quantum-inspired update and discrete operators.
- Add deterministic seeds, progress reporting, and cancellation.
- Test the algorithm against the common evaluator.
- Document its limitations and experimental assumptions.

### Milestone 4 — Persistence, API, and workers

- Create database models and migrations.
- Implement scenario-version persistence.
- Implement optimization-run persistence.
- Add Celery tasks and Redis configuration.
- Implement progress events, cancellation, failure handling, and result retrieval.
- Test the complete asynchronous execution lifecycle.

### Milestone 5 — Frontend foundation and design system

- Establish TRAFIQON branding and theme tokens.
- Implement the persistent workspace shell.
- Implement reusable panels, controls, typography, and status components.
- Integrate React Flow and custom road-network renderers.
- Connect the frontend to real backend endpoints.

### Milestone 6 — End-to-end operational workflow

- Implement the Command Center.
- Implement the Algorithm Lab.
- Implement the Scenario Studio.
- Implement the Experiment Explorer.
- Ensure each major control has real behavior and appropriate loading and error states.

### Milestone 7 — Simulation and incident-driven replanning

- Implement deterministic discrete-time simulation.
- Add authoritative vehicle movement.
- Add incident creation and resolution.
- Add route replanning while preserving vehicle state.
- Verify the full workflow with integration and end-to-end tests.

### Milestone 8 — Research presentation and hardening

- Complete convergence and benchmark visualizations.
- Complete exports and reproducibility metadata.
- Improve performance and accessibility.
- Run the complete test suite and production build.
- Review all documentation against actual behavior.
- Resolve critical defects and record any remaining limitations.

## 20. Definition of Done

TRAFIQON is not complete until all applicable criteria below have been verified.

### Functionality

- The application starts using the documented workflow.
- Database migrations run successfully from a clean database.
- Built-in scenarios load and can be inspected.
- Graph editing and scenario validation work.
- Dijkstra and A* return valid, tested shortest paths.
- Classical CVRP and Simulated Annealing return correctly evaluated results.
- The QPSO-inspired optimizer implements its documented update mechanism and is not merely a placeholder.
- All algorithms use a consistent evaluator and feasibility definition.
- Optimization runs execute through the worker system.
- Progress reflects real execution state.
- Cancellation and failure states work correctly.
- Results persist and can be retrieved after a page refresh.
- Simulation movement follows authoritative state.
- Incidents affect road costs or availability.
- Replanning preserves vehicle positions and completed stops.
- Benchmark comparisons and exports use actual stored results.

### Visual quality

- TRAFIQON branding is consistent throughout the application.
- The specified dark palette is implemented using centralized design tokens.
- The warm analytical theme is implemented coherently.
- The road network is the main visual focus.
- The interface follows the industrial-cartography design philosophy.
- No obsolete cyan/violet neon design remains.
- Charts have readable labels, units, legends, and meaningful data.
- All major controls are functional.
- Empty, loading, failure, and cancellation states are polished.
- Keyboard accessibility and reduced-motion behavior are supported.

### Engineering quality

- Relevant unit, integration, frontend, and end-to-end tests pass.
- Linting, formatting checks, and production builds pass where configured.
- No known critical defects remain in the required workflows.
- No fabricated metrics or unsupported claims appear in the application.
- Documentation reflects the actual implementation.
- The project can be reproduced using the documented setup.

Report incomplete items honestly. Do not mark a criterion complete solely because its UI exists.

## 21. First Action — Required Before Implementation

Begin by inspecting the repository and current environment.

Then provide:

1. A concise inventory of the existing codebase.
2. The proposed directory structure and component boundaries.
3. Any conflicts between the existing code and this specification.
4. Dependency and infrastructure compatibility findings.
5. A milestone implementation plan with acceptance criteria.
6. The most significant technical risks, especially discrete QPSO-inspired optimization, feasibility handling, and reliable job cancellation.
7. The smallest vertical slice to implement first.

The first vertical slice should be:

**Load a deterministic scenario → construct and validate the directed graph → execute a real routing operation → evaluate the resulting route → return the result through the API → display the actual route in React Flow.**

Implement tests for this vertical slice before expanding into every workspace.

If repository inspection reveals that the architecture needs a change, explain the reason and propose the smallest safe adjustment before making a major deviation.

After the initial plan, proceed milestone by milestone. At the end of each milestone, report:

- What was implemented.
- Which tests and commands actually ran.
- Their actual results.
- Known defects or incomplete requirements.
- Relevant architecture or algorithm decisions.
- The next milestone and its acceptance criteria.

Keep a concise, durable project-status document updated so work can resume after context resets.

**Final directive:** Build TRAFIQON as a technically honest, reproducible, well-engineered transportation research platform with an industrial-cartography identity. Prefer demonstrated correctness and real functionality over visual theater or unsupported research claims.