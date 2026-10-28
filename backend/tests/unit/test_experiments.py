import csv
import io
import json

import pytest
from helpers import line_scenario

from trafiqon.domain.serialization import scenario_fingerprint
from trafiqon.experiments import RunSpec, gap_percent, run_experiment
from trafiqon.experiments.baseline import main as baseline_main
from trafiqon.fixtures import load_builtin
from trafiqon.optimization import CancelFlag

SPECS = [
    RunSpec("simulated_annealing", {"max_iterations": 1500}),
    RunSpec("ortools_cvrp", {"time_limit_s": 0.2}),
]


@pytest.fixture(scope="module")
def report():
    return run_experiment(load_builtin("urban_grid"), SPECS, seeds=[0, 1, 2])


def test_runs_and_summaries(report):
    assert len(report.runs) == 6
    by_spec = {s.spec: s for s in report.summaries}
    assert set(by_spec) == {"simulated_annealing", "ortools_cvrp"}
    for s in report.summaries:
        assert s.n == 3 and s.feasible_count == 3 and s.feasible_rate == 1.0
        assert s.objective_best <= s.objective_median <= s.objective_worst
        assert s.objective_std is not None and s.objective_std >= 0
        assert s.gap_mean_percent >= 0
    sa_seeds = [r.seed for r in report.runs if r.algorithm_id == "simulated_annealing"]
    assert sa_seeds == [0, 1, 2]
    assert all(r.seed is None for r in report.runs if r.algorithm_id == "ortools_cvrp")


def test_reference_is_labelled_heuristic_and_is_the_best_run(report):
    ref = report.reference
    assert ref["kind"] == "best_observed_heuristic"
    assert ref["objective"] == min(r.objective for r in report.runs)


def test_metadata_supports_reproduction(report):
    meta = report.metadata
    assert meta["scenario_fingerprint"] == scenario_fingerprint(load_builtin("urban_grid"))
    assert meta["synthetic"] is True
    assert meta["seeds"] == [0, 1, 2]
    assert {"trafiqon", "python", "numpy", "ortools"} <= set(meta["software"])
    assert meta["evaluator_version"] == "1"


def test_sa_runs_reproduce_from_recorded_seed(report):
    again = run_experiment(load_builtin("urban_grid"), SPECS[:1], seeds=[0, 1, 2])
    first = [r.objective for r in report.runs if r.algorithm_id == "simulated_annealing"]
    assert [r.objective for r in again.runs] == first


def test_json_and_csv_exports(report):
    data = json.loads(json.dumps(report.to_json_dict()))
    assert data["quantity_kinds"]["elapsed_s"] == "measured"
    assert data["quantity_kinds"]["objective"] == "derived"
    assert len(data["runs"]) == 6
    rows = list(csv.DictReader(io.StringIO(report.runs_csv())))
    assert len(rows) == 6
    assert float(rows[0]["objective"]) == report.runs[0].objective
    assert rows[0]["algorithm_id"] == report.runs[0].algorithm_id


def test_infeasible_scenario_summary():
    rep = run_experiment(line_scenario(capacity=3, demands=(3, 4)), SPECS, seeds=[0])
    assert rep.reference is None
    for s in rep.summaries:
        assert s.feasible_rate == 0 and s.objective_mean is None and s.gap_mean_percent is None


def test_cancelled_experiment_stops():
    flag = CancelFlag()
    flag.cancel()
    rep = run_experiment(load_builtin("urban_grid"), SPECS, seeds=[0, 1], cancel=flag)
    assert rep.runs == () and rep.metadata["cancelled"] is True


def test_gap_percent():
    assert gap_percent(110, 100) == pytest.approx(10.0)
    assert gap_percent(100, 100) == 0
    with pytest.raises(ValueError):
        gap_percent(1, 0)


def test_baseline_cli_writes_exports(tmp_path, capsys):
    baseline_main(
        [
            "--seeds",
            "1",
            "--scenarios",
            "urban_grid",
            "--ortools-time-limit",
            "0.2",
            "--sa-iterations",
            "500",
            "--qpso-iterations",
            "2",
            "--out",
            str(tmp_path),
        ]
    )
    assert (tmp_path / "urban_grid.json").exists()
    assert (tmp_path / "urban_grid.csv").exists()
    assert "best_observed_heuristic" in capsys.readouterr().out


def test_ablation_specs_hold_everything_but_the_update_rule_equal():
    from trafiqon.experiments.ablation_qpso import specs

    by_label = {s.label: s.config for s in specs(ls_iterations=3, no_ls_iterations=4)}
    assert set(by_label) == {
        "qpso/no-ls",
        "uniform_resample/no-ls",
        "qpso/ls",
        "uniform_resample/ls",
    }
    for mode in ("no-ls", "ls"):
        q, a = by_label[f"qpso/{mode}"], by_label[f"uniform_resample/{mode}"]
        assert {k: v for k, v in q.items() if k != "update_rule"} == {
            k: v for k, v in a.items() if k != "update_rule"
        }
