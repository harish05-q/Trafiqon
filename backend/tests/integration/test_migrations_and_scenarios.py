import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from trafiqon.domain.serialization import scenario_fingerprint, scenario_from_dict
from trafiqon.persistence.models import Base


def test_migrated_schema_matches_models(engine):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_scenario_versions_are_immutable_in_the_database(client, engine, version_id):
    with engine.begin() as conn, pytest.raises(DBAPIError, match="immutable"):
        conn.execute(
            text("UPDATE scenario_versions SET note = 'x' WHERE id = :id"), {"id": version_id}
        )


def _data(client, builtin="urban_grid"):
    d = client.get(f"/api/v1/scenarios/builtin/{builtin}").json()
    for k in ("id", "name"):
        d.pop(k)
    return d


def test_create_from_builtin_and_from_data(client):
    r = client.post("/api/v1/scenarios", json={"name": "Grid", "builtin_id": "urban_grid"})
    assert r.status_code == 201
    body = r.json()
    assert r.headers["location"] == f"/api/v1/scenarios/{body['id']}"
    assert [v["version_number"] for v in body["versions"]] == [1]
    assert body["versions"][0]["synthetic"] is True

    r2 = client.post("/api/v1/scenarios", json={"name": "Custom", "data": _data(client)})
    assert r2.status_code == 201
    v = client.get(f"/api/v1/scenario-versions/{r2.json()['current_version_id']}").json()
    assert v["data"]["name"] == "Custom" and v["data"]["id"] == r2.json()["id"]
    assert v["fingerprint"] == scenario_fingerprint(scenario_from_dict(v["data"]))
    assert v["node_count"] == 30 and v["customer_count"] == 10


def test_versions_are_appended_not_mutated(client):
    sid = client.post("/api/v1/scenarios", json={"name": "S", "builtin_id": "urban_grid"}).json()[
        "id"
    ]
    data = _data(client)
    data["graph"]["edges"][0]["closed"] = True
    v2 = client.post(f"/api/v1/scenarios/{sid}/versions", json={"data": data, "note": "close"})
    assert v2.status_code == 201 and v2.json()["version_number"] == 2
    v1 = client.get(f"/api/v1/scenarios/{sid}/versions/1").json()
    assert not v1["data"]["graph"]["edges"][0]["closed"]
    assert v1["fingerprint"] != v2.json()["fingerprint"]
    detail = client.get(f"/api/v1/scenarios/{sid}").json()
    assert detail["current_version_id"] == v2.json()["id"]
    assert [v["version_number"] for v in detail["versions"]] == [1, 2]


def test_metadata_update_and_listing(client):
    ids = [
        client.post("/api/v1/scenarios", json={"name": f"S{i}", "builtin_id": "urban_grid"}).json()[
            "id"
        ]
        for i in range(3)
    ]
    r = client.patch(f"/api/v1/scenarios/{ids[0]}", json={"name": "Renamed"})
    assert r.json()["name"] == "Renamed" and len(r.json()["versions"]) == 1
    page = client.get("/api/v1/scenarios", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert (
        len(client.get("/api/v1/scenarios", params={"limit": 2, "offset": 2}).json()["items"]) == 1
    )


@pytest.mark.parametrize(
    ("mutate", "status", "code"),
    [
        (
            lambda d: d["graph"]["edges"].append(
                {**d["graph"]["edges"][0], "target": "nowhere", "id": "x"}
            ),
            422,
            "invalid_graph",
        ),
        (
            lambda d: d["customers"].append({"id": "cX", "node_id": "zz", "demand": 1}),
            422,
            "invalid_scenario",
        ),
        (lambda d: d["graph"]["edges"][0].update(distance=-1), 422, "validation_error"),
        (lambda d: d["vehicles"][0].update(start_depot_id="nope"), 422, "invalid_scenario"),
        (lambda d: d.update(extra=1), 422, "validation_error"),
    ],
)
def test_invalid_scenarios_rejected(client, mutate, status, code):
    data = _data(client)
    mutate(data)
    r = client.post("/api/v1/scenarios", json={"name": "bad", "data": data})
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code
    assert client.get("/api/v1/scenarios").json()["total"] == 0  # nothing persisted


def test_scenario_size_limit(client, factory, settings):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from trafiqon.api.app import create_app
    from trafiqon.settings import Limits

    small = TestClient(create_app(replace(settings, limits=Limits(max_nodes=10))))
    r = small.post("/api/v1/scenarios", json={"name": "big", "data": _data(client)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "scenario_too_large"


def test_exactly_one_source_and_unknown_ids(client):
    r = client.post("/api/v1/scenarios", json={"name": "x"})
    assert r.json()["error"]["code"] == "invalid_request"
    assert (
        client.post("/api/v1/scenarios", json={"name": "x", "builtin_id": "nope"}).status_code
        == 404
    )
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        client.get(f"/api/v1/scenarios/{missing}").json()["error"]["code"] == "scenario_not_found"
    )
    assert client.get(f"/api/v1/scenario-versions/{missing}").status_code == 404
    assert client.get("/api/v1/scenarios/not-a-uuid").status_code == 422


def test_delete_allowed_until_referenced(client, version_id):
    free = client.post("/api/v1/scenarios", json={"name": "F", "builtin_id": "urban_grid"}).json()[
        "id"
    ]
    assert client.delete(f"/api/v1/scenarios/{free}").status_code == 204
    assert client.get(f"/api/v1/scenarios/{free}").status_code == 404

    client.post(
        "/api/v1/runs",
        json={"scenario_version_id": version_id, "algorithm_id": "simulated_annealing"},
    )
    sid = client.get(f"/api/v1/scenario-versions/{version_id}").json()["scenario_id"]
    r = client.delete(f"/api/v1/scenarios/{sid}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "scenario_in_use"


def test_health_ready_and_metadata(client):
    assert client.get("/api/v1/health").json()["dependencies"]["database"]["status"] == "ok"
    assert client.get("/api/v1/ready").status_code == 200
    algs = {a["id"]: a for a in client.get("/api/v1/algorithms").json()}
    assert set(algs) == {"ortools_cvrp", "simulated_annealing", "qpso_hybrid"}
    assert algs["ortools_cvrp"]["uses_seed"] is False
    meta = client.get("/api/v1/meta").json()
    assert "database_url" not in str(meta) and meta["limits"]["max_queued_runs"] == 50
