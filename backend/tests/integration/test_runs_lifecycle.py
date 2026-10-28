import json
import threading
import time
import uuid

import pytest
from conftest import in_thread, wait_for
from sqlalchemy import func, select

from trafiqon.domain.solution import Solution, VehicleRoute
from trafiqon.persistence.db import session_scope
from trafiqon.persistence.models import RunEventRow, RunResultRow, RunRow, RunStatus
from trafiqon.persistence.runs import new_run
from trafiqon.persistence.scenarios import get_version, load_version_scenario
from trafiqon.routing import evaluate_solution

SA_FAST = {
    "algorithm_id": "simulated_annealing",
    "config": {"max_iterations": 2000, "progress_every": 200},
}


def submit(client, version_id, **body):
    payload = {"scenario_version_id": version_id, **SA_FAST, **body}
    return client.post("/api/v1/runs", json=payload)


def status_of(client, run_id):
    return client.get(f"/api/v1/runs/{run_id}").json()["status"]


def events(factory, run_id):
    with session_scope(factory) as s:
        return [
            (e.kind, e.type)
            for e in s.scalars(
                select(RunEventRow).where(RunEventRow.run_id == run_id).order_by(RunEventRow.id)
            )
        ]


def insert_run(factory, queue, version_id, algorithm_id="simulated_annealing", config=None, **kw):
    with session_scope(factory) as s:
        run = new_run(
            scenario_version_id=uuid.UUID(version_id),
            algorithm_id=algorithm_id,
            algorithm_version="1",
            config=config or SA_FAST["config"],
            seed=1,
            max_attempts=kw.pop("max_attempts", 2),
            **kw,
        )
        queue.enqueue(s, run)
        return run.id


# --- submission ---------------------------------------------------------------------------


def test_submit_persists_queued_run_before_ack(client, factory, version_id):
    r = submit(client, version_id)
    assert r.status_code == 202
    run = r.json()
    assert run["status"] == "QUEUED" and run["attempt"] == 0
    assert r.headers["location"] == f"/api/v1/runs/{run['id']}"
    assert isinstance(run["seed"], int)  # generated and recorded before execution
    assert run["config"]["max_iterations"] == 2000 and "moves" in run["config"]  # resolved
    assert events(factory, run["id"]) == [("lifecycle", "queued")]


def test_seed_not_recorded_for_seedless_algorithm(client, version_id):
    r = submit(
        client, version_id, algorithm_id="ortools_cvrp", config={"time_limit_s": 0.2}, seed=5
    )
    assert r.json()["seed"] is None


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"algorithm_id": "random_search"}, 422, "invalid_config"),
        ({"config": {"max_iterations": -1}}, 422, "invalid_config"),
        ({"config": {"bogus": 1}}, 422, "invalid_config"),
        ({"config": {"max_iterations": 10**9}}, 422, "invalid_config"),  # algorithm range
        ({"config": {"max_iterations": 5_000_000}}, 422, "config_exceeds_limits"),  # server
        (
            {"algorithm_id": "ortools_cvrp", "config": {"time_limit_s": 500}},
            422,
            "config_exceeds_limits",
        ),
        ({"algorithm_id": "ortools_cvrp", "config": {"time_limit_s": 900}}, 422, "invalid_config"),
        (
            {"algorithm_id": "qpso_hybrid", "config": {"swarm_size": 400}},
            422,
            "config_exceeds_limits",
        ),
        ({"seed": -1}, 422, "validation_error"),
        ({"scenario_version_id": str(uuid.uuid4())}, 404, "version_not_found"),
    ],
)
def test_submit_validation(client, version_id, body, status, code):
    r = submit(client, version_id, **body)
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code


def test_idempotent_submission(client, factory, version_id):
    a = submit(client, version_id, seed=3, idempotency_key="k-1")
    b = submit(client, version_id, seed=3, idempotency_key="k-1")
    assert a.status_code == 202 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]
    via_header = client.post(
        "/api/v1/runs",
        headers={"Idempotency-Key": "k-1"},
        json={"scenario_version_id": version_id, **SA_FAST, "seed": 3},
    )
    assert via_header.json()["id"] == a.json()["id"]
    conflict = submit(client, version_id, seed=4, idempotency_key="k-1")
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"
    )
    with session_scope(factory) as s:
        assert s.scalar(select(func.count()).select_from(RunRow)) == 1


def test_concurrent_idempotent_submissions_create_one_run(client, factory, version_id):
    results = []
    barrier = threading.Barrier(6)

    def go():
        barrier.wait()
        results.append(submit(client, version_id, seed=9, idempotency_key="race").json()["id"])

    threads = [threading.Thread(target=go) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 1
    with session_scope(factory) as s:
        assert s.scalar(select(func.count()).select_from(RunRow)) == 1


def test_queue_limit(client, version_id, settings):
    for _ in range(settings.limits.max_queued_runs):
        assert submit(client, version_id).status_code == 202
    r = submit(client, version_id)
    assert r.status_code == 429 and r.json()["error"]["code"] == "queue_full"


def test_list_and_filter(client, version_id):
    for alg in ("simulated_annealing", "simulated_annealing", "qpso_hybrid"):
        submit(client, version_id, algorithm_id=alg, config={})
    page = client.get("/api/v1/runs", params={"algorithm_id": "simulated_annealing"}).json()
    assert page["total"] == 2
    assert client.get("/api/v1/runs", params={"status": "QUEUED", "limit": 1}).json()["total"] == 3
    assert client.get("/api/v1/runs", params={"status": "BOGUS"}).status_code == 422


# --- execution ----------------------------------------------------------------------------


def test_worker_completes_run_and_result_matches_evaluator(
    client, factory, make_worker, version_id
):
    run_id = submit(client, version_id).json()["id"]
    assert (
        client.get(f"/api/v1/runs/{run_id}/result").json()["error"]["code"]
        == "result_not_available"
    )
    assert make_worker().run_once() is RunStatus.COMPLETED
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "COMPLETED" and run["attempt"] == 1 and run["finished_at"]
    assert run["termination_reason"] == "iteration_limit"
    result = client.get(f"/api/v1/runs/{run_id}/result").json()
    assert result["feasible"] and result["seed"] == run["seed"]
    assert result["diagnostics"]["software"]["ortools"]
    # Re-score the stored routes against the stored scenario version.
    with session_scope(factory) as s:
        scenario = load_version_scenario(get_version(s, uuid.UUID(version_id)))
    sol = Solution(
        tuple(
            VehicleRoute(
                r["vehicle_id"], tuple(r["customer_ids"]), r["start_depot_id"], r["end_depot_id"]
            )
            for r in result["solution"]["routes"]
        )
    )
    assert evaluate_solution(scenario, sol).objective == pytest.approx(result["objective"])
    assert all(
        leg["edge_ids"] is not None for r in result["evaluation"]["routes"] for leg in r["legs"]
    )
    kinds = events(factory, run_id)
    assert kinds[0] == ("lifecycle", "queued") and kinds[1] == ("lifecycle", "started")
    assert ("progress", "progress") in kinds and kinds[-1] == ("lifecycle", "completed")


def test_same_seed_reproduces_through_the_worker(client, make_worker, version_id):
    a = submit(client, version_id, seed=11).json()["id"]
    b = submit(client, version_id, seed=11).json()["id"]
    worker = make_worker()
    worker.run_once(), worker.run_once()
    ra, rb = (client.get(f"/api/v1/runs/{x}/result").json() for x in (a, b))
    assert ra["objective"] == rb["objective"] and ra["solution"] == rb["solution"]


def test_progress_events_are_bounded(client, factory, make_worker, version_id, settings):
    from trafiqon.settings import Limits

    run_id = submit(
        client, version_id, config={"max_iterations": 20000, "progress_every": 10}
    ).json()["id"]
    make_worker(limits=Limits(max_progress_events_per_run=5)).run_once()
    progress = [e for e in events(factory, run_id) if e[0] == "progress"]
    assert len(progress) == 5
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["progress"]["iteration"] > 0 and "percent" not in json.dumps(run["progress"])


def test_sse_stream_replays_and_resumes(client, make_worker, version_id):
    run_id = submit(client, version_id).json()["id"]
    make_worker().run_once()
    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    blocks = [b for b in text.strip().split("\n\n") if b and not b.startswith(":")]
    ids = [int(b.split("\n")[0][4:]) for b in blocks if b.startswith("id: ")]
    assert ids == sorted(ids) and len(ids) >= 4
    assert blocks[-1].startswith("event: end") and '"COMPLETED"' in blocks[-1]
    assert "event: started" in text and "event: progress" in text and "event: completed" in text
    with client.stream(
        "GET", f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": str(ids[-2])}
    ) as r:
        resumed = "".join(r.iter_text())
    assert f"id: {ids[-1]}\n" in resumed and f"id: {ids[-2]}\n" not in resumed


def test_sse_streams_live_progress_while_running(client, make_worker, version_id):
    run_id = submit(
        client, version_id, config={"max_iterations": 400_000, "progress_every": 2000}
    ).json()["id"]
    t, _ = in_thread(make_worker().run_once)
    seen = []
    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as r:
        for line in r.iter_lines():
            if line.startswith("event: "):
                seen.append(line[7:])
                if seen.count("progress") == 3:
                    client.post(f"/api/v1/runs/{run_id}/cancel")
            if line.startswith("event: end"):
                break
    t.join(10)
    assert seen[:2] == ["queued", "started"] and "progress" in seen
    assert "cancel_requested" in seen and seen[-2:] == ["cancelled", "end"]


# --- cancellation and terminal states -----------------------------------------------------


def test_cancel_queued_run(client, make_worker, version_id):
    run_id = submit(client, version_id).json()["id"]
    r = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert r.status_code == 202 and r.json()["status"] == "CANCELLED"
    again = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert again.status_code == 200 and again.json()["status"] == "CANCELLED"
    assert make_worker().run_once() is None  # nothing to claim
    assert client.get(f"/api/v1/runs/{run_id}/result").status_code == 404


def test_cancel_running_run_stops_cooperatively_and_ends_cancelled(client, make_worker, version_id):
    run_id = submit(client, version_id, config={"max_iterations": 2_000_000}).json()["id"]
    t, out = in_thread(make_worker().run_once)
    wait_for(lambda: status_of(client, run_id) == "RUNNING")
    started = time.monotonic()
    r = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert r.status_code == 202 and r.json()["status"] == "CANCELLING"
    t.join(10)
    assert out == [RunStatus.CANCELLED]
    assert time.monotonic() - started < 3  # heartbeat interval 0.05 s + loop check
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "CANCELLED" and run["termination_reason"] == "cancelled"
    result = client.get(f"/api/v1/runs/{run_id}/result").json()
    assert result["termination_reason"] == "cancelled" and result["iterations"] < 2_000_000
    assert client.post(f"/api/v1/runs/{run_id}/cancel").json()["status"] == "CANCELLED"


def test_terminal_states_are_never_overwritten(factory, queue, version_id, client):
    run_id = insert_run(factory, queue, version_id)
    claim = queue.claim("w1")
    result = {
        "feasible": True,
        "objective": 1.0,
        "total_distance": 1.0,
        "solution": None,
        "evaluation": None,
        "iterations": 1,
        "evaluations": 1,
        "elapsed_s": 0.1,
        "time_to_first_feasible_s": 0.0,
        "termination_reason": "iteration_limit",
        "optimality": "not_proven",
        "seed": 1,
        "history": [],
        "diagnostics": {},
    }
    # A cancel arrives while running; the algorithm then finishes normally (delayed): the
    # run must end CANCELLED, not COMPLETED.
    with session_scope(factory) as s:
        assert queue.request_cancel(s, claim.id) is RunStatus.CANCELLING
    assert queue.complete(claim.id, "w1", result) is RunStatus.CANCELLED
    # Late writes after terminal state are all no-ops.
    assert queue.complete(claim.id, "w1", result) is None
    assert queue.fail(claim.id, "w1", {"code": "late"}) is None
    assert queue.report_progress(claim.id, "w1", {"iteration": 99}, True) is False
    assert queue.heartbeat(claim.id, "w1") is None
    with session_scope(factory) as s:
        assert queue.request_cancel(s, claim.id) is RunStatus.CANCELLED
        run = s.get(RunRow, run_id)
        assert run.status == RunStatus.CANCELLED and run.error is None
        assert s.scalar(select(func.count()).select_from(RunResultRow)) == 1


def test_only_the_owner_can_finish_a_run(factory, queue, version_id):
    insert_run(factory, queue, version_id)
    claim = queue.claim("owner")
    assert queue.complete(claim.id, "intruder", {"termination_reason": "x"}) is None
    assert queue.fail(claim.id, "intruder", {}) is None
    assert queue.heartbeat(claim.id, "intruder") is None
    assert queue.heartbeat(claim.id, "owner") is RunStatus.RUNNING


def test_completed_run_cannot_be_cancelled_or_failed(
    client, factory, queue, make_worker, version_id
):
    run_id = submit(client, version_id).json()["id"]
    make_worker().run_once()
    r = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    with session_scope(factory) as s:
        assert s.get(RunRow, uuid.UUID(run_id)).cancel_requested_at is None


# --- failures and recovery ----------------------------------------------------------------


class Boom:
    id, version, uses_seed, defaults = "boom", "1", False, {}

    def resolve_config(self, config):
        return dict(config)

    def run(self, inp):
        raise RuntimeError("kaboom: internal detail")


def test_worker_exception_marks_run_failed_without_leaking_traceback(
    client, factory, queue, make_worker, version_id
):
    run_id = insert_run(factory, queue, version_id, algorithm_id="boom", config={})
    assert make_worker(algorithms={"boom": Boom()}).run_once() is RunStatus.FAILED
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "FAILED" and run["termination_reason"] == "error"
    assert run["error"] == {
        "code": "algorithm_error",
        "type": "RuntimeError",
        "message": "kaboom: internal detail",
    }
    assert "Traceback" not in json.dumps(run)
    assert events(factory, run_id)[-1] == ("lifecycle", "failed")


def test_unknown_algorithm_in_queue_fails_cleanly(client, factory, queue, make_worker, version_id):
    run_id = insert_run(factory, queue, version_id, algorithm_id="removed_algo", config={})
    assert make_worker().run_once() is RunStatus.FAILED
    assert client.get(f"/api/v1/runs/{run_id}").json()["error"]["code"] == "unknown_algorithm"


def test_stale_run_is_requeued_then_failed_after_max_attempts(factory, queue, version_id):
    run_id = insert_run(factory, queue, version_id, max_attempts=2)
    first = queue.claim("dead-1")
    time.sleep(0.7)  # > stale_after_s (0.5) without heartbeats
    assert queue.recover_stale() == [(run_id, RunStatus.QUEUED)]
    second = queue.claim("dead-2")
    assert second.id == run_id and second.attempt == 2
    # The first (stale) worker comes back: it no longer owns the run.
    assert queue.heartbeat(first.id, "dead-1") is None
    assert queue.complete(first.id, "dead-1", {"termination_reason": "iteration_limit"}) is None
    time.sleep(0.7)
    assert queue.recover_stale() == [(run_id, RunStatus.FAILED)]
    with session_scope(factory) as s:
        run = s.get(RunRow, run_id)
        assert run.status == RunStatus.FAILED and run.termination_reason == "worker_lost"
        assert run.error["code"] == "worker_lost"
    assert [t for k, t in events(factory, run_id) if k == "lifecycle"] == [
        "queued",
        "started",
        "requeued",
        "started",
        "failed",
    ]


def test_stale_cancelling_run_becomes_cancelled(factory, queue, version_id):
    run_id = insert_run(factory, queue, version_id)
    queue.claim("dead")
    with session_scope(factory) as s:
        queue.request_cancel(s, run_id)
    time.sleep(0.7)
    assert queue.recover_stale() == [(run_id, RunStatus.CANCELLED)]


def test_live_worker_is_not_recovered(client, make_worker, queue, version_id):
    run_id = submit(client, version_id, config={"max_iterations": 2_000_000}).json()["id"]
    t, _ = in_thread(make_worker().run_once)
    wait_for(lambda: status_of(client, run_id) == "RUNNING")
    time.sleep(0.8)  # longer than stale_after_s, but heartbeats keep it fresh
    assert queue.recover_stale() == []
    client.post(f"/api/v1/runs/{run_id}/cancel")
    t.join(10)


def test_requeued_run_executes_once_more_and_stores_one_result(
    client, factory, queue, make_worker, version_id
):
    run_id = submit(client, version_id).json()["id"]
    queue.claim("dead")
    time.sleep(0.7)
    queue.recover_stale()
    assert make_worker("alive").run_once() is RunStatus.COMPLETED
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["attempt"] == 2 and run["status"] == "COMPLETED"
    with session_scope(factory) as s:
        assert s.scalar(select(func.count()).select_from(RunResultRow)) == 1


# --- queue concurrency (needs real PostgreSQL row locking) ---------------------------------


def test_skip_locked_claims_each_run_exactly_once(factory, queue, version_id):
    ids = {insert_run(factory, queue, version_id) for _ in range(40)}
    claimed: list = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def claimer(n):
        barrier.wait()
        while (c := queue.claim(f"w{n}")) is not None:
            with lock:
                claimed.append((c.id, n))

    threads = [threading.Thread(target=claimer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(c for c, _ in claimed) == sorted(ids)  # every run, exactly once
    assert len({n for _, n in claimed}) > 1  # work was actually shared between workers


def test_claim_versus_cancel_race_never_loses_the_cancel(factory, queue, version_id):
    outcomes = set()
    for i in range(30):
        run_id = insert_run(factory, queue, version_id)
        barrier = threading.Barrier(2)
        res: dict = {}

        def claim(i=i, barrier=barrier, res=res):
            barrier.wait()
            res["claim"] = queue.claim(f"w{i}")

        def cancel(barrier=barrier, res=res, run_id=run_id):
            barrier.wait()
            with session_scope(factory) as s:
                res["cancel"] = queue.request_cancel(s, run_id)

        ts = [threading.Thread(target=claim), threading.Thread(target=cancel)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        with session_scope(factory) as s:
            final = s.get(RunRow, run_id).status
        if res["claim"] is None:  # cancel won: the run was never handed to a worker
            assert final == RunStatus.CANCELLED == res["cancel"]
        else:  # claim won: the worker sees CANCELLING on its next heartbeat
            assert final == RunStatus.CANCELLING == res["cancel"]
            assert queue.heartbeat(run_id, f"w{i}") is RunStatus.CANCELLING
        outcomes.add(final)
    assert outcomes <= {RunStatus.CANCELLED, RunStatus.CANCELLING}


def test_prune_keeps_lifecycle_events(client, factory, queue, make_worker, version_id):
    run_id = submit(client, version_id).json()["id"]
    make_worker().run_once()
    assert queue.prune_progress_events(older_than_days=0) > 0
    remaining = events(factory, run_id)
    assert remaining and all(k == "lifecycle" for k, _ in remaining)
