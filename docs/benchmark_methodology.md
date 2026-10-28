# Benchmark methodology (as implemented, M2)

Code: `backend/src/trafiqon/experiments/`.

CLI:

```bash
cd backend && uv run python -m trafiqon.experiments.baseline --seeds 5 --out results/baseline
```

## Procedure
- **Same inputs for every run:** `run_experiment(scenario, specs, seeds)` builds the cost matrix once and runs every spec once per seed, on the same scenario object and matrix.
- **Algorithms without a seed:** OR-Tools takes no seed, so it is simply repeated `len(seeds)` times and its seed is recorded as `null`.
- **Recorded metadata** (enough to reproduce the experiment):
  - timestamp
  - scenario id and SHA-256 fingerprint of the canonical scenario JSON
  - whether the scenario is synthetic
  - seeds
  - specs with their configs
  - evaluator version
  - versions of trafiqon, Python, NumPy and OR-Tools, and the platform
- **Per run:**
  - spec, algorithm id and version, seed, repetition, and resolved config
  - feasibility, objective and total distance (from the shared evaluator)
  - wall time and time to first feasible
  - evaluations and iterations
  - termination reason and optimality

## Quantity kinds
- **measured:** wall-clock times (`elapsed_s`, `time_to_first_feasible_s`). These depend on the machine and its load.
- **derived:** objective and distance (shared evaluator), evaluations and iterations (counted), summary statistics, and gap.

No quantity is estimated or simulated in M2. Exports include a `quantity_kinds` map.

## Budgets are not equal (explicit difference)
- **OR-Tools** is limited by wall time (`time_limit_s`, CLI default 1.0 s). It exposes no evaluation count.
- **SA** is limited by iterations (CLI default 20,000 proposed moves). Iterations keep it deterministic per seed; its wall time is recorded.

Comparisons of objective quality should be read together with the recorded wall times. A budget-matched comparison (e.g. SA with `time_limit_s` equal to OR-Tools' limit) can be run by passing configs to `run_experiment`, at the cost of SA determinism.

## Statistics (per spec)
- n, feasible count and feasible rate.
- Over feasible runs only: objective mean, median, sample standard deviation (n−1; omitted when fewer than 2 runs), best and worst.
- Wall time mean and median.

## Optimality gap
`gap% = 100 * (objective - reference) / reference`, defined only for a positive reference.

The reference is:
- `proven_optimum` if any run in the experiment returned `optimality = proven_optimal`;
- otherwise `best_observed_heuristic`, the best feasible objective observed in this experiment.

A `best_observed_heuristic` gap is relative to a heuristic result. It is not a gap to the optimum, and it is labelled as such in exports. No lower bounds are computed yet.

## Exports
- `ExperimentReport.to_json_dict()`: metadata, reference, quantity kinds, runs, and summaries.
- `ExperimentReport.runs_csv()`: one row per run.

The CLI writes `<scenario>.json` and `<scenario>.csv`. `backend/results/` is git-ignored: results are machine-specific measurements.

## Fixtures
- The built-in scenarios (Urban Grid, Congested City, Incident Response) are **small synthetic** fixtures: 25–36 nodes and 8–12 customers.
- No larger experimental scenarios exist yet.
