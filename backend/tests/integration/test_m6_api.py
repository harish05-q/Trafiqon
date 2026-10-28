from datetime import UTC, datetime, timedelta


def test_algorithms_publish_params_capped_by_server_limits(client):
    algs = {a["id"]: a for a in client.get("/api/v1/algorithms").json()}
    ort = {p["key"]: p for p in algs["ortools_cvrp"]["params"]}
    assert ort["time_limit_s"]["maximum"] == 120  # algorithm allows 600, server caps at 120
    assert ort["time_limit_s"]["default"] == 2.0
    assert "GUIDED_LOCAL_SEARCH" in ort["local_search_metaheuristic"]["choices"]
    qpso = {p["key"]: p for p in algs["qpso_hybrid"]["params"]}
    assert qpso["swarm_size"]["maximum"] == 100
    assert "ABLATION" in qpso["update_rule"]["description"]
    sa = {p["key"]: p for p in algs["simulated_annealing"]["params"]}
    assert sa["cooling_rate"]["nullable"] and sa["cooling_rate"]["null_meaning"].startswith("auto")
    for a in algs.values():
        assert [p["key"] for p in a["params"]] == list(a["defaults"])


def _data(client, builtin="urban_grid"):
    d = client.get(f"/api/v1/scenarios/builtin/{builtin}").json()
    for k in ("id", "name"):
        d.pop(k)
    return d


def test_validate_valid_scenario(client):
    r = client.post("/api/v1/scenarios/validate", json=_data(client))
    assert r.status_code == 200
    v = r.json()
    assert v["valid"] and v["feasible_so_far"]
    assert v["strongly_connected_components"] == 1
    assert v["unreachable_location_pairs"] == 0
    assert v["total_demand"] == 36 and v["total_capacity"] == 45
    assert client.get("/api/v1/scenarios").json()["total"] == 0  # nothing saved


def test_validate_reports_errors_infeasibility_and_warnings(client):
    data = _data(client)
    data["customers"].append({"id": "cX", "node_id": "nowhere", "demand": 1})
    v = client.post("/api/v1/scenarios/validate", json=data).json()
    assert not v["valid"]
    assert any(i["code"] == "unknown_node" and i["severity"] == "error" for i in v["issues"])

    data = _data(client)
    data["customers"][0]["demand"] = 99
    v = client.post("/api/v1/scenarios/validate", json=data).json()
    assert v["valid"] and not v["feasible_so_far"]
    assert {i["code"] for i in v["issues"]} >= {"demand_exceeds_capacity"}

    data = _data(client)
    for e in data["graph"]["edges"]:  # cut every road into node n0_1
        if e["target"] == "n0_1":
            e["closed"] = True
    v = client.post("/api/v1/scenarios/validate", json=data).json()
    codes = {i["code"]: i["severity"] for i in v["issues"]}
    assert codes["customer_unreachable"] == "infeasible"
    assert codes["not_strongly_connected"] == "warning"
    assert v["strongly_connected_components"] > 1 and v["unreachable_location_pairs"] > 0

    data = _data(client)
    data["graph"]["edges"].append({**data["graph"]["edges"][0], "target": "ghost", "id": "g"})
    v = client.post("/api/v1/scenarios/validate", json=data).json()
    assert not v["valid"] and v["issues"][0]["code"] == "invalid_graph"


def test_run_filters_by_scenario_and_date(client, version_id):
    other = client.post(
        "/api/v1/scenarios", json={"name": "Other", "builtin_id": "congested_city"}
    ).json()
    for vid in (version_id, version_id, other["current_version_id"]):
        client.post(
            "/api/v1/runs", json={"scenario_version_id": vid, "algorithm_id": "simulated_annealing"}
        )
    sid = client.get(f"/api/v1/scenario-versions/{version_id}").json()["scenario_id"]
    assert client.get("/api/v1/runs", params={"scenario_id": sid}).json()["total"] == 2
    assert client.get("/api/v1/runs", params={"scenario_id": other["id"]}).json()["total"] == 1
    now = datetime.now(UTC)
    later = (now + timedelta(hours=1)).isoformat()
    earlier = (now - timedelta(hours=1)).isoformat()
    assert client.get("/api/v1/runs", params={"created_after": later}).json()["total"] == 0
    assert client.get("/api/v1/runs", params={"created_after": earlier}).json()["total"] == 3
    assert client.get("/api/v1/runs", params={"created_before": earlier}).json()["total"] == 0
