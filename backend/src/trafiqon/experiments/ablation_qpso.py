"""QPSO update-rule ablation (docs/algorithms.md, "Ablation hook").

Compares the QPSO update with independent uniform key resampling under the SAME decode,
repair, local search, swarm size and iteration count (equal particle evaluations), with
local search off (isolates the update rule) and on (the default hybrid).

    uv run python -m trafiqon.experiments.ablation_qpso --seeds 5 --out results/ablation
"""

from __future__ import annotations

import argparse
from pathlib import Path

from trafiqon.experiments.runner import RunSpec, format_report, run_experiment, write_report
from trafiqon.fixtures import load_builtin
from trafiqon.fixtures.builtin import experimental_grid


def specs(ls_iterations: int, no_ls_iterations: int) -> list[RunSpec]:
    out = []
    for rule in ("qpso", "uniform_resample"):
        out.append(
            RunSpec(
                "qpso_hybrid",
                {"update_rule": rule, "local_search_passes": 0, "iterations": no_ls_iterations},
                label=f"{rule}/no-ls",
            )
        )
    for rule in ("qpso", "uniform_resample"):
        out.append(
            RunSpec(
                "qpso_hybrid",
                {"update_rule": rule, "swarm_size": 15, "iterations": ls_iterations},
                label=f"{rule}/ls",
            )
        )
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--ls-iterations", type=int, default=30)
    parser.add_argument("--no-ls-iterations", type=int, default=100)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    seeds = list(range(args.seeds))
    for scenario in (load_builtin("congested_city"), experimental_grid(0)):
        report = run_experiment(scenario, specs(args.ls_iterations, args.no_ls_iterations), seeds)
        if args.out:
            write_report(report, args.out, scenario.id)
        print("\n" + format_report(report, scenario.id))


if __name__ == "__main__":
    main()
