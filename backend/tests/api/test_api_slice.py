import pytest
from fastapi.testclient import TestClient

from trafiqon.api.app import create_app
from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin
from trafiqon.routing import shortest_path


@pytest.fixture
def client():
    return TestClient(create_app(cors_origins=["http://localhost:3000"]))


def test_health_reports_database_not_configured(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["database"]["status"] == "not_configured"


def test_list_builtin(client):
    r = client.get("/api/v1/scenarios/builtin")
    assert r.status_code == 200
    items = {s["id"]: s for s in r.json()}
    assert set(items) == set(BUILTIN_SCENARIOS)
    grid = items["urban_grid"]
    assert grid["synthetic"] is True
    assert grid["node_count"] == len(load_builtin("urban_grid").graph.nodes)


def test_get_builtin_returns_full_graph(client):
    r = client.get("/api/v1/scenarios/builtin/incident_response")
    assert r.status_code == 200
    body = r.json()
    s = load_builtin("incident_response")
    assert len(body["graph"]["edges"]) == len(s.graph.edges)
    assert {e["id"] for e in body["graph"]["edges"] if e["closed"]} == {
        e.id for e in s.graph.edges.values() if e.closed
    }


def test_unknown_scenario_uses_error_shape(client):
    r = client.get("/api/v1/scenarios/builtin/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "scenario_not_found"


@pytest.mark.parametrize("algorithm", ["dijkstra", "astar"])
def test_shortest_path_matches_core_and_is_valid(client, algorithm):
    req = {"scenario_id": "urban_grid", "source": "n2_2", "target": "n5_0", "algorithm": algorithm}
    r = client.post("/api/v1/routing/shortest-path", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["reachable"] is True
    expected = shortest_path(load_builtin("urban_grid").graph, "n2_2", "n5_0")
    assert body["path"]["travel_time"] == pytest.approx(expected.travel_time)
    assert body["path"]["node_ids"][0] == "n2_2" and body["path"]["node_ids"][-1] == "n5_0"
    assert len(body["path"]["edge_ids"]) == len(body["path"]["node_ids"]) - 1
    assert body["expanded_nodes"] > 0


def test_shortest_path_avoids_incident_closures(client):
    req = {"scenario_id": "incident_response", "source": "n2_1", "target": "n2_2"}
    body = client.post("/api/v1/routing/shortest-path", json=req).json()
    closed = {e.id for e in load_builtin("incident_response").graph.edges.values() if e.closed}
    assert body["reachable"]
    assert not closed & set(body["path"]["edge_ids"])
    assert len(body["path"]["edge_ids"]) > 1  # direct edge is closed


def test_same_source_and_target(client):
    req = {"scenario_id": "urban_grid", "source": "n1_1", "target": "n1_1"}
    body = client.post("/api/v1/routing/shortest-path", json=req).json()
    assert body["path"] == {"node_ids": ["n1_1"], "edge_ids": [], "travel_time": 0, "distance": 0}


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        ({"scenario_id": "urban_grid", "source": "zz", "target": "n1_1"}, 422, "unknown_node"),
        ({"scenario_id": "nope", "source": "a", "target": "b"}, 404, "scenario_not_found"),
        (
            {"scenario_id": "urban_grid", "source": "n1_1", "target": "n1_2", "algorithm": "bfs"},
            422,
            "validation_error",
        ),
        ({"scenario_id": "urban_grid", "source": "n1_1"}, 422, "validation_error"),
        (
            {"scenario_id": "urban_grid", "source": "n1_1", "target": "n1_2", "extra": 1},
            422,
            "validation_error",
        ),
    ],
)
def test_shortest_path_errors(client, payload, status, code):
    r = client.post("/api/v1/routing/shortest-path", json=payload)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code


def test_cors_allows_configured_origin(client):
    r = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_openapi_lists_slice_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/api/v1/health",
        "/api/v1/scenarios/builtin",
        "/api/v1/scenarios/builtin/{scenario_id}",
        "/api/v1/routing/shortest-path",
    } <= set(paths)
