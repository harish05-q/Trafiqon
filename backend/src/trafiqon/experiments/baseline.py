"""Baseline experiment CLI: OR-Tools, SA and the QPSO-inspired hybrid on the built-in
(small synthetic) scenarios.

    uv run python -m trafiqon.experiments.baseline --seeds 5 --out results/baseline

Writes <scenario>.json and <scenario>.csv per scenario and prints the summaries.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from trafiqon.experiments.runner import RunSpec, format_report, run_experiment, write_report
from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=5, help="repetitions (seeds 0..n-1)")
    parser.add_argument("--scenarios", nargs="*", default=sorted(BUILTIN_SCENARIOS))
    parser.add_argument("--ortools-time-limit", type=float, default=1.0)
    parser.add_argument("--sa-iterations", type=int, default=20_000)
    parser.add_argument("--qpso-iterations", type=int, default=100)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    specs = [
        RunSpec("ortools_cvrp", {"time_limit_s": args.ortools_time_limit}),
        RunSpec("simulated_annealing", {"max_iterations": args.sa_iterations}),
        RunSpec("qpso_hybrid", {"iterations": args.qpso_iterations}),
    ]
    seeds = list(range(args.seeds))
    for scenario_id in args.scenarios:
        report = run_experiment(load_builtin(scenario_id), specs, seeds)
        if args.out:
            write_report(report, args.out, scenario_id)
        print("\n" + format_report(report, scenario_id))


if __name__ == "__main__":
    main()
