import copy
import math

import pytest
from helpers import line_scenario

from trafiqon.domain import Solution, Vehicle, VehicleRoute
from trafiqon.fixtures import load_builtin
from trafiqon.simulation import (
    Leg,
    PlannedRoute,
    SimStatus,
    Simulation,
    SimulationError,
    SimulationSession,
    VehicleStatus,
    construction_routes,
    replan,
    routes_from_solution,
)


def line_sim(tick=0.5) -> Simulation:
    """v1 serves A then B on the line scenario: d->a (2), a->b (3), b->a->d (3+2) = 10 min."""
    s = line_scenario()
    routes = routes_from_solution(s, Solution((VehicleRoute("v1", ("A", "B"), "D", "D"),)))
    return Simulation(s, routes, tick)


def completion_times(sim):
    return {c["customer_id"]: c["time"] for v in sim.vehicles.values() for c in v.completed}


# --- movement ------------------------------------------------------------------------------


def test_exact_arrival_times_and_finish():
    sim = line_sim()
    sim.start()
    sim.step(3)  # t = 1.5: 75 % along d->a
    v = sim.vehicles["v1"]
    assert v.on_edge == "d->a" and v.progress == pytest.approx(0.75)
    sim.step(1)  # t = 2.0: arrives at a, completes A at exactly 2.0
    assert completion_times(sim) == {"A": 2.0}
    sim.step(6)  # t = 5.0: B
    assert completion_times(sim) == {"A": 2.0, "B": 5.0}
    sim.step(9)
    assert sim.status is SimStatus.RUNNING and v.status is VehicleStatus.EN_ROUTE
    sim.step(1)  # t = 10: back at the depot
    assert v.status is VehicleStatus.FINISHED and sim.status is SimStatus.FINISHED
    assert v.node == "d" and v.distance_km == pytest.approx(10.0)
    assert v.driving_min == pytest.approx(10.0) and v.load_delivered == 7
    sim.step(5)  # finished simulations do not advance
    assert sim.tick == 20


@pytest.mark.parametrize("tick", [0.1, 0.25, 0.7, 1.0, 3.0])
def test_results_do_not_depend_on_tick_size(tick):
    sim = line_sim(tick)
    sim.start()
    sim.step(math.ceil(10 / tick) + 1)
    assert completion_times(sim) == pytest.approx({"A": 2.0, "B": 5.0})
    assert sim.vehicles["v1"].driving_min == pytest.approx(10.0)


def test_no_teleporting_each_tick_moves_at_most_dt():
    s = load_builtin("congested_city")
    sim = Simulation(s, construction_routes(s), 0.5)
    sim.start()
    prev = {vid: (v.driving_min, v.distance_km) for vid, v in sim.vehicles.items()}
    while sim.status is not SimStatus.FINISHED:
        sim.step()
        for vid, v in sim.vehicles.items():
            assert v.driving_min - prev[vid][0] <= sim.tick_minutes + 1e-9
            if v.on_edge:
                assert 0.0 <= v.progress < 1.0
            prev[vid] = (v.driving_min, v.distance_km)
    # Driving time equals the evaluator's planned travel time when nothing changes.
    planned = sum(
        sim.graph.edges[e].current_time
        for r in construction_routes(s)
        for leg in r.legs
        for e in leg.edge_ids
    )
    assert sum(v.driving_min for v in sim.vehicles.values()) == pytest.approx(planned)


def test_traffic_change_on_current_edge_keeps_progress_and_retimes_the_rest():
    sim = line_sim()
    sim.start()
    sim.step(7)  # t = 3.5: halfway along a->b (3 min edge)
    v = sim.vehicles["v1"]
    assert v.on_edge == "a->b" and v.progress == pytest.approx(0.5)
    sim.set_traffic("a->b", 2.0)  # edge now takes 6 min: 3 min remain instead of 1.5
    assert v.progress == pytest.approx(0.5)
    assert sim.position(v)["remaining_on_edge_min"] == pytest.approx(3.0)
    sim.step(13)
    assert completion_times(sim)["B"] == pytest.approx(6.5)


def test_closure_of_current_edge_lets_vehicle_finish_it():
    sim = line_sim()
    sim.start()
    sim.step(7)
    sim.set_closed("a->b", True)
    sim.step(3)
    assert completion_times(sim)["B"] == 5.0  # finished the edge it was already on


def test_closed_next_edge_blocks_until_reopened():
    sim = line_sim()
    sim.start()
    sim.step(8)  # t = 4.0, on a->b
    sim.set_closed("b->a", True)
    sim.step(4)  # t = 6: arrived at b (5.0), completed B, blocked on b->a
    v = sim.vehicles["v1"]
    assert v.status is VehicleStatus.BLOCKED and v.node == "b"
    assert [e["type"] for e in sim.events].count("vehicle_blocked") == 1
    sim.step(4)  # still waiting; no driving time accrues
    assert v.node == "b" and v.driving_min == pytest.approx(5.0)
    sim.set_closed("b->a", False)
    sim.step(10)  # t = 13: 5 more minutes of driving after reopening at t = 8
    assert v.status is VehicleStatus.FINISHED
    assert any(e["type"] == "vehicle_unblocked" and e["time"] == 8.0 for e in sim.events)


# --- road layers and incidents --------------------------------------------------------------


def test_condition_layers_compose_and_resolve_exactly():
    sim = line_sim()
    orig = sim.graph.edges["a->b"].current_time
    sim.set_traffic("a->b", 1.5)
    inc = sim.add_incident(["a->b"], "slowdown", 2.0)
    assert sim.graph.edges["a->b"].current_time == pytest.approx(orig * 3.0)
    sim.resolve_incident(inc.id)
    assert sim.graph.edges["a->b"].current_time == pytest.approx(orig * 1.5)
    sim.set_traffic("a->b", 1.0)
    assert sim.graph.edges["a->b"].current_time == orig

    sim.set_closed("d->a", True)
    closure = sim.add_incident(["d->a"], "closure")
    sim.resolve_incident(closure.id)
    assert sim.graph.edges["d->a"].closed  # the manual closure is still in force
    sim.set_closed("d->a", False)
    assert not sim.graph.edges["d->a"].closed
    assert sim.resolve_incident(closure.id).resolved_tick == 0  # idempotent


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.add_incident([], "closure"),
        lambda s: s.add_incident(["nope"], "closure"),
        lambda s: s.add_incident(["a->b"], "flood"),
        lambda s: s.add_incident(["a->b"], "slowdown", 0.5),
        lambda s: s.set_traffic("a->b", 0),
        lambda s: s.set_traffic("a->b", float("inf")),
        lambda s: s.resolve_incident("inc-99"),
        lambda s: s.pause(),
        lambda s: s.resume(),
        lambda s: s.step(-1),
    ],
)
def test_invalid_commands_rejected(call):
    with pytest.raises(SimulationError):
        call(line_sim())


# --- replanning ------------------------------------------------------------------------------


def first_moving_vehicle(sim):
    return next(v for v in sim.vehicles.values() if v.status is VehicleStatus.EN_ROUTE and v.legs)


def test_replan_routes_around_a_closure_and_preserves_state():
    s = load_builtin("urban_grid")
    sim = Simulation(s, construction_routes(s), 0.5)
    sim.start()
    sim.step(9)
    v = first_moving_vehicle(sim)
    blocked_edge = v.remaining_edges()[0]
    before = {vid: (copy.deepcopy(x.completed), sim.position(x), x.distance_km)
              for vid, x in sim.vehicles.items()}  # fmt: skip
    t, tick = sim.time, sim.tick
    sim.add_incident([blocked_edge], "closure")
    result = replan(sim)
    assert (sim.time, sim.tick) == (t, tick)  # clock untouched
    for vid, x in sim.vehicles.items():
        assert (x.completed, sim.position(x), x.distance_km) == before[vid]  # nothing lost or moved
    assert blocked_edge not in v.remaining_edges()
    assert result["unserved"] == [] and result["plan_version"] == 1
    assert result["latency_ms"] >= 0 and result["quantity_kinds"]["latency_ms"] == "measured"
    sim.step(2000)
    assert sim.status is SimStatus.FINISHED
    assert sorted(c["customer_id"] for x in sim.vehicles.values() for c in x.completed) == sorted(
        c.id for c in s.customers
    )


def test_replan_starts_after_the_edge_in_progress():
    sim = line_sim()
    sim.start()
    sim.step(7)  # halfway along a->b
    replan(sim)
    v = sim.vehicles["v1"]
    assert v.on_edge == "a->b" and v.progress == pytest.approx(0.5)
    assert v.legs[0].stop_id == "B" and v.legs[0].edge_ids == []  # B is the edge's target
    sim.step(20)
    assert completion_times(sim) == {"A": 2.0, "B": 5.0}


def test_exact_replan_is_never_worse_than_keeping_the_old_order():
    from trafiqon.routing import dijkstra

    s = load_builtin("congested_city")
    for tick_count in (3, 8, 15):
        sim = Simulation(s, construction_routes(s), 0.5)
        sim.start()
        sim.step(tick_count)
        for v in sim.vehicles.values():  # heavy slowdown on everyone's next planned roads
            for e in v.remaining_edges()[:4]:
                sim.set_traffic(e, 6.0)
        old_orders = {vid: v.remaining_stops() for vid, v in sim.vehicles.items()}
        result = replan(sim)
        customers = {c.id: c.node_id for c in s.customers}
        for p in result["vehicles"]:
            v = sim.vehicles[p["vehicle_id"]]
            # Cost of the OLD order under the NEW conditions, from the same origin.
            at, old_cost = p["origin_node"], 0.0
            for stop in [*old_orders[v.id], None]:
                target = customers[stop] if stop else v.end_node
                old_cost += dijkstra(sim.graph, at).time[target]
                at = target
            assert p["remaining_time_min"] <= old_cost + 1e-9
            assert sorted(p["new_stops"]) == sorted(old_orders[v.id])


def test_unreachable_stop_is_reported_unserved_then_recovered():
    sim = line_sim()
    sim.start()
    sim.step(1)
    inc = sim.add_incident(["a->b", "d->b"], "closure")  # b unreachable
    r = replan(sim)
    v = sim.vehicles["v1"]
    assert r["unserved"] == ["B"] and v.unserved == ["B"]
    assert v.remaining_stops() == ["A"]
    sim.step(40)
    assert sim.status is SimStatus.FINISHED and completion_times(sim) == {"A": 2.0}
    sim.resolve_incident(inc.id)
    replan(sim)  # previously unserved stops are retried
    assert v.unserved == [] and v.remaining_stops() == ["B"]
    assert v.status is VehicleStatus.EN_ROUTE


def test_stranded_vehicle_is_reported_not_rerouted_through_closures():
    sim = line_sim()
    sim.start()
    sim.step(9)  # on a->b, A done, B is at the edge's target
    sim.add_incident(["b->a"], "closure")  # b has no other exit
    r = replan(sim)
    assert r["vehicles"][0]["end_depot_reachable"] is False
    assert r["vehicles"][0]["remaining_time_min"] is None
    assert r["unserved"] == []  # B is at the vehicle's own node: still served
    sim.step(50)
    v = sim.vehicles["v1"]
    assert completion_times(sim)["B"] == 5.0
    assert v.status is VehicleStatus.BLOCKED and v.node == "b"
    assert any(e["type"] == "vehicle_stranded" for e in sim.events)
    assert sim.status is SimStatus.RUNNING  # honest: never "finished" while stranded


def test_large_remaining_set_uses_heuristic_and_stays_complete():
    s = load_builtin("urban_grid")
    from dataclasses import replace

    s = replace(s, vehicles=(Vehicle("v1", 100, "d1"),))
    sim = Simulation(s, construction_routes(s), 0.5)
    assert len(sim.vehicles["v1"].remaining_stops()) == 10  # > EXACT_LIMIT
    r = replan(sim)
    assert sorted(r["vehicles"][0]["new_stops"]) == sorted(c.id for c in s.customers)
    sim.start()
    sim.step(5000)
    assert sim.status is SimStatus.FINISHED and len(sim.vehicles["v1"].completed) == 10


# --- determinism, reset, plans ----------------------------------------------------------------


def run_script(sim):
    sim.start()
    sim.step(5)
    sim.add_incident(["n2_2->n2_3"], "slowdown", 3.0)
    sim.step(4)
    replan(sim)
    sim.step(30)
    return [
        (v.id, v.node, v.on_edge, round(v.progress, 12), v.completed) for v in sim.vehicles.values()
    ], [{k: e[k] for k in e if k != "latency_ms"} for e in sim.events]


def test_same_commands_same_state():
    s = load_builtin("urban_grid")
    assert run_script(Simulation(s, construction_routes(s), 0.5)) == run_script(
        Simulation(s, construction_routes(s), 0.5)
    )


def test_reset_restores_initial_state():
    s = load_builtin("urban_grid")
    sim = Simulation(s, construction_routes(s), 0.5)
    initial = [(v.id, v.node, v.remaining_stops()) for v in sim.vehicles.values()]
    run_script(sim)
    sim.reset()
    assert sim.time == 0 and sim.tick == 0 and sim.status is SimStatus.READY
    assert not sim.incidents and sim.graph is s.graph and sim.plan_version == 0
    assert [(v.id, v.node, v.remaining_stops()) for v in sim.vehicles.values()] == initial


def test_infeasible_or_broken_plans_are_rejected():
    s = line_scenario(capacity=5)
    with pytest.raises(SimulationError, match="capacity_exceeded"):
        routes_from_solution(s, Solution((VehicleRoute("v1", ("A", "B"), "D", "D"),)))
    s = line_scenario()
    bad = [PlannedRoute("v1", "D", "D", [Leg("A", "a", ["a->b"])])]
    with pytest.raises(SimulationError, match="discontinuous"):
        Simulation(s, bad)
    with pytest.raises(SimulationError, match="tick_minutes"):
        Simulation(s, [], 0)


def test_unrouted_vehicles_are_idle():
    sim = line_sim()
    assert sim.vehicles["v2"].status is VehicleStatus.IDLE


# --- real-time session ---------------------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_session_converts_wall_time_to_whole_ticks_with_carry():
    clock = FakeClock()
    session = SimulationSession(line_sim(0.5), speed=1.0, clock=clock)
    session.control("start")
    clock.t += 1.2  # 1.2 simulated minutes at speed 1 -> 2 ticks, 0.2 carried
    session.sync()
    assert session.sim.tick == 2
    clock.t += 0.3  # 0.2 + 0.3 = 0.5 -> 1 more tick
    session.sync()
    assert session.sim.tick == 3
    session.control("speed", speed=10.0)
    clock.t += 0.5  # 5 simulated minutes -> 10 ticks
    session.sync()
    assert session.sim.tick == 13


def test_session_pause_step_resume_and_errors():
    clock = FakeClock()
    session = SimulationSession(line_sim(0.5), clock=clock)
    session.control("start")
    session.control("pause")
    clock.t += 50
    session.sync()
    assert session.sim.tick == 0  # paused: wall time does not advance the simulation
    session.control("step", ticks=4)
    assert session.sim.tick == 4
    session.control("resume")
    with pytest.raises(SimulationError, match="pause before stepping"):
        session.control("step")
    with pytest.raises(SimulationError):
        session.control("speed", speed=3.0)
    with pytest.raises(SimulationError):
        session.control("teleport")
    clock.t += 100
    session.sync()
    assert session.sim.status is SimStatus.FINISHED and session.sim.tick == 20
    assert session.control("replan")["plan_version"] == 1
