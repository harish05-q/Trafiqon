import csv
import io

import pytest

SPECS = [
    {"algorithm_id": "simulated_annealing", "config": {"max_iterations": 1500}},
    {"algorithm_id": "qpso_hybrid", "config": {"swarm_size": 6, "iterations": 4}, "label": "qpso"},
    {"algorithm_id": "ortools_cvrp", "config": {"time_limit_s": 0.2}},
]


def launch(client, version_id, **body):
    payload = {
        "name": "baseline",
        "scenario_version_id": version_id,
        "specs": SPECS,
        "repetitions": 2,
        "budget_policy": "SA iterations, QPSO particles, OR-Tools time",
    }
    return client.post("/api/v1/suites", json={**payload, **body})


def drain(worker):
    while worker.run_once() is not None:
        pass


def test_launch_creates_all_runs_atomically(client, version_id):
    r = launch(client, version_id)
    assert r.status_code == 202
    suite = r.json()
    assert len(suite["run_ids"]) == 6 and suite["status_counts"] == {"QUEUED": 6}
    assert suite["seeds"] == [0, 1]
    runs = client.get("/api/v1/runs", params={"suite_id": suite["id"], "limit": 100}).json()[
        "items"
    ]
    seeds = {(r["suite_spec"], r["repetition"]): r["seed"] for r in runs}
    assert seeds[("simulated_annealing", 1)] == 1 and seeds[("ortools_cvrp", 1)] is None


def test_comparison_and_exports_use_stored_results(client, make_worker, version_id):
    suite = launch(client, version_id).json()
    partial = client.get(f"/api/v1/suites/{suite['id']}/comparison").json()
    assert partial["complete"] is False and partial["reference"] is None

    drain(make_worker())
    cmp_ = client.get(f"/api/v1/suites/{suite['id']}/comparison").json()
    assert cmp_["complete"] is True
    assert cmp_["reference"]["kind"] == "best_observed_heuristic"
    assert len(cmp_["runs"]) == 6  # seed-level rows of COMPLETED runs, for charts
    assert {r["spec"] for r in cmp_["runs"]} == {"simulated_annealing", "qpso", "ortools_cvrp"}
    by_spec = {s["spec"]: s for s in cmp_["summaries"]}
    assert set(by_spec) == {"simulated_annealing", "qpso", "ortools_cvrp"}
    assert all(s["n"] == 2 and s["feasible_rate"] == 1.0 for s in by_spec.values())

    stored = {}
    for run_id in suite["run_ids"]:
        res = client.get(f"/api/v1/runs/{run_id}/result").json()
        stored[run_id] = res["objective"]
    assert cmp_["reference"]["objective"] == min(stored.values())

    exported = client.get(f"/api/v1/suites/{suite['id']}/export", params={"format": "json"})
    assert exported.headers["content-disposition"].endswith('.json"')
    data = exported.json()
    assert sorted(r["objective"] for r in data["runs"]) == sorted(stored.values())
    assert data["metadata"]["scenario_fingerprint"] and data["metadata"]["software"]
    assert data["quantity_kinds"]["elapsed_s"] == "measured"

    rows = list(
        csv.DictReader(
            io.StringIO(
                client.get(f"/api/v1/suites/{suite['id']}/export", params={"format": "csv"}).text
            )
        )
    )
    assert sorted(float(r["objective"]) for r in rows) == sorted(stored.values())


def test_cancelled_and_failed_runs_are_counted_not_imputed(client, make_worker, version_id):
    suite = launch(client, version_id, repetitions=1).json()
    client.post(f"/api/v1/runs/{suite['run_ids'][0]}/cancel")
    drain(make_worker())
    cmp_ = client.get(f"/api/v1/suites/{suite['id']}/comparison").json()
    counts = cmp_["status_counts_by_spec"]
    cancelled_spec = next(spec for spec, c in counts.items() if c.get("CANCELLED"))
    summary = next(s for s in cmp_["summaries"] if s["spec"] == cancelled_spec)
    assert summary["n"] == 0 and summary["objective_mean"] is None
    assert cmp_["complete"] is True


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"repetitions": 20}, "suite_too_large"),  # 3 x 20 > 30
        ({"repetitions": None}, "invalid_request"),
        ({"seeds": [1, 2], "repetitions": 3}, "invalid_request"),
        ({"specs": [SPECS[0], SPECS[0]]}, "duplicate_spec_label"),
        ({"specs": [{"algorithm_id": "nope"}]}, "invalid_config"),
        (
            {"specs": [{"algorithm_id": "ortools_cvrp", "config": {"time_limit_s": 300}}]},
            "config_exceeds_limits",
        ),
    ],
)
def test_suite_validation(client, version_id, body, code):
    r = launch(client, version_id, **body)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == code
    assert client.get("/api/v1/runs").json()["total"] == 0  # nothing partially created


def test_explicit_seeds_and_listing(client, version_id):
    r = launch(client, version_id, seeds=[7, 42], repetitions=None)
    assert r.json()["seeds"] == [7, 42]
    assert client.get("/api/v1/suites").json()["total"] == 1
    assert client.get(f"/api/v1/suites/{r.json()['id']}").json()["repetitions"] == 2
    assert client.get("/api/v1/suites/00000000-0000-0000-0000-000000000000").status_code == 404


def test_suite_blocks_scenario_deletion(client, version_id):
    launch(client, version_id)
    sid = client.get(f"/api/v1/scenario-versions/{version_id}").json()["scenario_id"]
    assert client.delete(f"/api/v1/scenarios/{sid}").status_code == 409
