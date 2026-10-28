import time

import pytest


def create(client, version_id, **body):
    return client.post("/api/v1/simulations", json={"scenario_version_id": version_id, **body})


def ctl(client, sid, action, **kw):
    return client.post(f"/api/v1/simulations/{sid}/control", json={"action": action, **kw})


def test_create_from_construction_and_step(client, version_id):
    r = create(client, version_id)
    assert r.status_code == 201, r.text
    s = r.json()
    assert r.headers["location"] == f"/api/v1/simulations/{s['id']}"
    assert s["status"] == "ready" and s["time_min"] == 0 and s["plan_source"] == "construction"
    assert s["customer_count"] == 10 and s["served_count"] == 0
    assert all(v["node"] == "n2_2" for v in s["vehicles"])  # urban_grid depot
    s = ctl(client, s["id"], "step", ticks=6).json()
    assert s["tick"] == 6 and s["time_min"] == 3.0 and s["status"] == "ready"
    moving = [v for v in s["vehicles"] if v["edge_id"] or v["node"] != "n2_2"]
    assert moving and all(v["x"] is not None for v in moving)
    assert s["quantity_kinds"]["time_min"] == "simulated"


def test_create_from_completed_run_uses_its_routes(client, make_worker, version_id):
    run = client.post(
        "/api/v1/runs",
        json={
            "scenario_version_id": version_id,
            "algorithm_id": "simulated_annealing",
            "config": {"max_iterations": 2000},
            "seed": 3,
        },
    ).json()
    queued = create(client, version_id, run_id=run["id"])
    assert queued.status_code == 409 and queued.json()["error"]["code"] == "no_feasible_solution"
    make_worker().run_once()
    result = client.get(f"/api/v1/runs/{run['id']}/result").json()
    s = create(client, version_id, run_id=run["id"]).json()
    assert s["plan_source"] == "run" and s["run_id"] == run["id"]
    planned = {
        r["vehicle_id"]: [e for leg in r["legs"] for e in leg["edge_ids"]]
        for r in result["evaluation"]["routes"]
    }
    for v in s["vehicles"]:
        if v["id"] in planned:
            assert v["remaining_edge_ids"] == planned[v["id"]]
    # Run it to the end in steps: every customer served, simulated driving == objective.
    s = ctl(client, s["id"], "step", ticks=2000).json()
    assert s["status"] == "finished" and s["served_count"] == 10
    assert sum(v["driving_min"] for v in s["vehicles"]) == pytest.approx(result["objective"])


def test_incident_and_replan_preserve_progress(client, version_id):
    s = create(client, version_id).json()
    sid = s["id"]
    s = ctl(client, sid, "step", ticks=9).json()
    v = next(x for x in s["vehicles"] if len(x["remaining_edge_ids"]) > 2)
    ahead = v["remaining_edge_ids"][1]
    before = {
        x["id"]: (x["completed"], x["node"], x["edge_id"], x["progress"]) for x in s["vehicles"]
    }
    r = client.post(
        f"/api/v1/simulations/{sid}/incidents", json={"edge_ids": [ahead], "kind": "closure"}
    )
    assert r.status_code == 201
    s = r.json()
    assert (
        s["incidents"][0]["active"]
        and {"edge_id": ahead, "closed": True}.items() <= s["road_overrides"][0].items()
    )
    rep = client.post(f"/api/v1/simulations/{sid}/replan").json()
    assert rep["replan"]["plan_version"] == 1 and rep["replan"]["latency_ms"] >= 0
    s = rep["state"]
    assert s["time_min"] == 4.5 and s["tick"] == 9
    for x in s["vehicles"]:
        assert (x["completed"], x["node"], x["edge_id"], x["progress"]) == before[x["id"]]
    v_after = next(x for x in s["vehicles"] if x["id"] == v["id"])
    assert ahead not in v_after["remaining_edge_ids"]
    s = client.post(f"/api/v1/simulations/{sid}/incidents/inc-1/resolve").json()
    assert s["incidents"][0]["active"] is False and s["road_overrides"] == []


def test_roads_traffic_and_closure(client, version_id):
    sid = create(client, version_id).json()["id"]
    s = client.post(
        f"/api/v1/simulations/{sid}/roads",
        json={"edge_id": "n0_1->n0_2", "traffic_factor": 2.0, "closed": True},
    ).json()
    o = s["road_overrides"][0]
    assert o["closed"] and o["current_time"] == pytest.approx(2 * o["original_current_time"])
    assert s["traffic_factors"] == {"n0_1->n0_2": 2.0} and s["manual_closures"] == ["n0_1->n0_2"]
    s = client.post(
        f"/api/v1/simulations/{sid}/roads",
        json={"edge_id": "n0_1->n0_2", "closed": False, "traffic_factor": 1.0},
    ).json()
    assert s["road_overrides"] == []
    bad = client.post(f"/api/v1/simulations/{sid}/roads", json={"edge_id": "nope", "closed": True})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "simulation_rejected"
    assert (
        client.post(f"/api/v1/simulations/{sid}/roads", json={"edge_id": "n0_1->n0_2"}).status_code
        == 422
    )


def test_controls_state_machine_and_real_time_advance(client, version_id):
    sid = create(client, version_id, speed=30.0).json()["id"]
    assert ctl(client, sid, "pause").status_code == 409
    assert ctl(client, sid, "start").json()["status"] == "running"
    assert ctl(client, sid, "step").json()["error"]["code"] == "invalid_simulation_state"
    time.sleep(0.4)  # ~12 simulated minutes at 30 min/s
    s = client.get(f"/api/v1/simulations/{sid}").json()
    assert s["tick"] > 0 and s["status"] in ("running", "finished")
    s = ctl(client, sid, "pause").json()
    paused_tick = s["tick"]
    time.sleep(0.2)
    assert client.get(f"/api/v1/simulations/{sid}").json()["tick"] == paused_tick
    assert ctl(client, sid, "speed", speed=3.0).status_code == 422  # not an offered speed
    assert ctl(client, sid, "speed", speed=2.0).json()["speed"] == 2.0
    s = ctl(client, sid, "reset").json()
    assert s["tick"] == 0 and s["status"] == "ready" and s["incidents"] == []


def test_errors_limits_and_delete(client, version_id, settings):
    assert create(client, "00000000-0000-0000-0000-000000000000").status_code == 404
    assert create(client, version_id, tick_minutes=0).status_code == 422
    assert client.get("/api/v1/simulations/nope").json()["error"]["code"] == "simulation_not_found"
    r = client.post("/api/v1/simulations/x/incidents", json={"edge_ids": [], "kind": "closure"})
    assert r.status_code == 422
    sids = [create(client, version_id).json()["id"] for _ in range(settings.limits.max_simulations)]
    over = create(client, version_id)
    assert over.status_code == 429 and over.json()["error"]["code"] == "too_many_simulations"
    assert len(client.get("/api/v1/simulations").json()) == settings.limits.max_simulations
    assert client.delete(f"/api/v1/simulations/{sids[0]}").status_code == 204
    assert client.get(f"/api/v1/simulations/{sids[0]}").status_code == 404
    assert create(client, version_id).status_code == 201
