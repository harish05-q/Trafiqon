"""Baseline experiment CLI: OR-Tools and SA on the built-in (synthetic) scenarios.

    uv run python -m trafiqon.experiments.baseline --seeds 5 --out results/baseline

Writes <scenario>.json and <scenario>.csv per scenario and prints the summaries.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trafiqon.experiments.runner import RunSpec, run_experiment
from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=5, help="repetitions (seeds 0..n-1)")
    parser.add_argument("--scenarios", nargs="*", default=sorted(BUILTIN_SCENARIOS))
    parser.add_argument("--ortools-time-limit", type=float, default=1.0)
    parser.add_argument("--sa-iterations", type=int, default=20_000)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    specs = [
        RunSpec("ortools_cvrp", {"time_limit_s": args.ortools_time_limit}),
        RunSpec("simulated_annealing", {"max_iterations": args.sa_iterations}),
    ]
    seeds = list(range(args.seeds))
    for scenario_id in args.scenarios:
        report = run_experiment(load_builtin(scenario_id), specs, seeds)
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{scenario_id}.json").write_text(
                json.dumps(report.to_json_dict(), indent=2), encoding="utf-8"
            )
            (args.out / f"{scenario_id}.csv").write_text(report.runs_csv(), encoding="utf-8")
        ref = report.reference
        print(
            f"\n{scenario_id} (synthetic={report.metadata['synthetic']}) reference: "
            f"{ref['objective']:.3f} min [{ref['kind']}]"
            if ref
            else f"\n{scenario_id}: no feasible run"
        )
        print(
            f"{'spec':<22}{'n':>3}{'feas':>6}{'mean':>10}{'median':>10}{'std':>8}"
            f"{'best':>10}{'gap%':>8}{'time s':>8}"
        )
        for s in report.summaries:

            def f(x, w, p=3):
                return f"{x:>{w}.{p}f}" if x is not None else f"{'-':>{w}}"

            print(
                f"{s.spec:<22}{s.n:>3}{s.feasible_rate:>6.0%}{f(s.objective_mean, 10)}"
                f"{f(s.objective_median, 10)}{f(s.objective_std, 8)}{f(s.objective_best, 10)}"
                f"{f(s.gap_mean_percent, 8, 2)}{f(s.elapsed_mean_s, 8, 2)}"
            )


if __name__ == "__main__":
    main()
