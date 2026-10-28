import math
import random
import statistics

import pytest
from helpers import edge, graph
from test_optimization import two_islands

from trafiqon.domain import Customer, Depot, Scenario, Vehicle
from trafiqon.fixtures import load_builtin
from trafiqon.optimization import AlgorithmInput, CancelFlag, ConfigError, TerminationReason
from trafiqon.optimization.operators import local_search, repair, unreachable_legs
from trafiqon.optimization.problem import RoutingProblem, cheapest_insertion
from trafiqon.optimization.qpso import QpsoHybrid, clip, decode, encode, qpso_update
from trafiqon.routing import build_scenario_matrix, evaluate_solution

SMALL = {"swarm_size": 8, "iterations": 10}


def problem_for(scenario):
    return RoutingProblem(scenario, build_scenario_matrix(scenario))


def random_routes(rng, n, v):
    routes = [[] for _ in range(v)]
    order = list(range(n))
    rng.shuffle(order)
    for c in order:
        routes[rng.randrange(v)].append(c)
    return routes


# --- encoding / decoding ------------------------------------------------------------------


def test_decode_encode_round_trip_is_exact():
    rng = random.Random(0)
    for _ in range(200):
        n, v = rng.randint(1, 15), rng.randint(1, 5)
        routes = random_routes(rng, n, v)
        assert decode(encode(routes, n), n, v) == routes


def test_decode_rules():
    n, v = 4, 2
    #      assignment keys       | order keys
    x = [0.2, 1.999999, 1.0, 0.0, 0.9, 0.1, 0.5, 0.9]
    # vehicle 0: customers 0 (0.9), 3 (0.9) -> tie by index; vehicle 1: 1 (0.1), 2 (0.5)
    assert decode(x, n, v) == [[0, 3], [1, 2]]
    # keys at the upper clip bound still map to the last vehicle
    assert decode(clip([5.0] * n + [2.0] * n, n, v), n, v)[1] == [0, 1, 2, 3]


def test_clip_bounds():
    n, v = 3, 2
    x = clip([-1.0, 2.5, 1.2, -0.1, 0.4, 7.0], n, v)
    assert x[0] == 0.0 and x[1] < 2 and x[2] == 1.2
    assert x[3:] == [0.0, 0.4, 1.0]


# --- QPSO update rule ---------------------------------------------------------------------


def test_update_is_stationary_at_converged_swarm():
    x = [0.3, 1.7, 0.5]
    assert qpso_update(x, x, x, x, beta=1.0, rng=random.Random(1)) == pytest.approx(x, abs=1e-12)


def test_update_with_zero_beta_samples_the_local_attractor_segment():
    rng = random.Random(2)
    x, pb, gb, mb = [5.0], [1.0], [3.0], [9.0]
    samples = [qpso_update(x, pb, gb, mb, 0.0, rng)[0] for _ in range(2000)]
    assert min(samples) >= 1.0 and max(samples) <= 3.0
    assert statistics.fmean(samples) == pytest.approx(2.0, abs=0.05)  # E[phi] = 1/2


@pytest.mark.parametrize("beta", [0.5, 1.0])
def test_update_step_length_matches_delta_well_distribution(beta):
    # With pbest = gbest = p, x' - p = +/- beta*L*ln(1/u); E|x'-p| = beta*L (E[ln 1/u] = 1),
    # and the sign is symmetric.
    rng = random.Random(3)
    p, x, mbest = 0.0, 1.0, 3.0  # L = |mbest - x| = 2
    steps = [qpso_update([x], [p], [p], [mbest], beta, rng)[0] - p for _ in range(40_000)]
    assert statistics.fmean(abs(s) for s in steps) == pytest.approx(beta * 2.0, rel=0.03)
    assert abs(statistics.fmean(steps)) < 0.05 * beta * 2.0
    assert all(math.isfinite(s) for s in steps)


def test_update_is_deterministic_for_rng_state():
    args = ([0.1, 0.9], [0.2, 0.8], [0.3, 0.4], [0.5, 0.5], 0.8)
    assert qpso_update(*args, rng=random.Random(9)) == qpso_update(*args, rng=random.Random(9))


# --- repair -------------------------------------------------------------------------------


def test_repair_fixes_capacity_and_keeps_every_customer_once():
    s = load_builtin("congested_city")
    p = problem_for(s)
    everything_on_one = [list(range(p.n_customers))] + [[] for _ in range(p.n_vehicles - 1)]
    assert p.overload(everything_on_one) > 0
    fixed, ok = repair(p, everything_on_one)
    assert ok
    assert sorted(c for r in fixed for c in r) == list(range(p.n_customers))
    assert p.overload(fixed) == 0
    assert evaluate_solution(s, p.to_solution(fixed)).feasible


def test_repair_fixes_unreachable_legs():
    s = two_islands()
    p = problem_for(s)
    # vehicle 0 is "vq" on island Q; give it island-P customers.
    idx = {c: i for i, c in enumerate(p.customer_ids)}
    bad = [[idx["A1"], idx["B1"]], [idx["A2"]]]
    assert unreachable_legs(p, 0, bad[0]) > 0
    fixed, ok = repair(p, bad)
    assert ok
    assert evaluate_solution(s, p.to_solution(fixed)).feasible


def test_repair_is_identity_on_feasible_routes():
    s = load_builtin("urban_grid")
    p = problem_for(s)
    routes = cheapest_insertion(p)
    assert repair(p, routes) == (routes, True)


def bin_packing_trap() -> Scenario:
    """Passes the capacity pre-checks (each demand <= 5, total 9 <= 10) but cannot be packed."""
    g = graph(["d", "a", "b", "c"], [e for x in "abc" for e in (edge("d", x, 1), edge(x, "d", 1))])
    return Scenario(
        id="trap",
        name="trap",
        graph=g,
        depots=(Depot("D", "d"),),
        customers=tuple(Customer(x.upper(), x, 3) for x in "abc"),
        vehicles=(Vehicle("v1", 5, "D"), Vehicle("v2", 5, "D")),
    )


def test_repair_reports_failure_honestly():
    p = problem_for(bin_packing_trap())
    routes, ok = repair(p, [[0, 1, 2], []])
    assert not ok
    assert sorted(c for r in routes for c in r) == [0, 1, 2]
    assert p.overload(routes) > 0


def test_unpackable_scenario_yields_no_solution_not_a_fake_one():
    r = QpsoHybrid().run(AlgorithmInput(bin_packing_trap(), SMALL, seed=0))
    assert not r.feasible and r.solution is None and r.objective is None
    assert r.termination_reason is TerminationReason.NO_SOLUTION_FOUND
    assert r.diagnostics["repairs_failed"] > 0


# --- local search -------------------------------------------------------------------------


def test_local_search_preserves_feasibility_and_never_worsens():
    s = load_builtin("congested_city")
    p = problem_for(s)
    rng = random.Random(4)
    for _ in range(20):
        routes, ok = repair(p, random_routes(rng, p.n_customers, p.n_vehicles))
        assert ok
        improved, moves = local_search(p, routes, passes=3)
        assert moves > 0
        assert p.overload(improved) == 0
        assert p.total_cost(improved) <= p.total_cost(routes) + 1e-9
        assert evaluate_solution(s, p.to_solution(improved)).feasible


def test_local_search_result_is_a_local_optimum():
    p = problem_for(load_builtin("urban_grid"))
    routes, _ = repair(p, random_routes(random.Random(5), p.n_customers, p.n_vehicles))
    optimum, _ = local_search(p, routes, passes=50)
    again, _ = local_search(p, optimum, passes=1)
    assert again == optimum


def test_zero_passes_is_a_no_op():
    p = problem_for(load_builtin("urban_grid"))
    routes = cheapest_insertion(p)
    assert local_search(p, routes, passes=0) == (routes, 0)


# --- optimizer ----------------------------------------------------------------------------


def run(scenario, seed=0, **cfg):
    return QpsoHybrid().run(AlgorithmInput(scenario, {**SMALL, **cfg}, seed=seed))


def test_deterministic_for_seed_and_records_generated_seed():
    s = load_builtin("congested_city")
    a, b = run(s, seed=7), run(s, seed=7)
    assert a.solution == b.solution and a.objective == b.objective
    assert a.evaluations == b.evaluations
    assert a.diagnostics["diversity"] == b.diagnostics["diversity"]
    gen = run(s, seed=None)
    assert isinstance(gen.seed, int)
    assert run(s, seed=gen.seed).objective == gen.objective


def test_matches_shared_evaluator_and_tracks_budget():
    s = load_builtin("incident_response")
    r = run(s, iterations=6)
    assert r.feasible
    assert r.objective == evaluate_solution(s, r.solution).objective
    assert r.diagnostics["internal_best_travel_time"] == pytest.approx(r.objective)
    assert r.iterations == 6
    assert r.diagnostics["particle_evaluations"] == 8 * 6 + 8
    assert len(r.diagnostics["diversity"]) == 6
    assert len(r.history) == 7  # initial swarm + one point per iteration


def test_swarm_contracts_under_qpso_but_not_under_resampling_ablation():
    s = load_builtin("congested_city")
    q = run(s, iterations=40, swarm_size=12)
    a = run(s, iterations=40, swarm_size=12, update_rule="uniform_resample")
    assert q.diagnostics["diversity"][-1] < 0.6 * q.diagnostics["diversity"][0]
    assert a.diagnostics["diversity"][-1] > 0.8 * a.diagnostics["diversity"][0]


@pytest.mark.parametrize(
    "cfg",
    [
        {"lamarckian": False},
        {"local_search_passes": 0},
        {"seed_with_construction": False},
        {"beta_start": 0.8, "beta_end": 0.8},
    ],
)
def test_variants_stay_feasible(cfg):
    s = load_builtin("urban_grid")
    r = run(s, **cfg)
    assert r.feasible and evaluate_solution(s, r.solution).feasible


@pytest.mark.parametrize(
    "cfg",
    [
        {"swarm_size": 1},
        {"iterations": 0},
        {"beta_start": -1},
        {"lamarckian": "yes"},
        {"update_rule": "random_search"},
        {"inertia": 0.7},
    ],
)
def test_invalid_config(cfg):
    with pytest.raises(ConfigError):
        QpsoHybrid().resolve_config(cfg)


def test_cancellation_before_and_during():
    s = load_builtin("urban_grid")
    pre = CancelFlag()
    pre.cancel()
    r = QpsoHybrid().run(AlgorithmInput(s, SMALL, seed=0, cancel=pre))
    assert r.termination_reason is TerminationReason.CANCELLED
    assert r.iterations == 0 and not r.feasible

    flag, seen = CancelFlag(), []

    def progress(e):
        seen.append(e)
        if e.iteration == 2:
            flag.cancel()

    r = QpsoHybrid().run(
        AlgorithmInput(s, {**SMALL, "iterations": 50}, seed=0, cancel=flag, progress=progress)
    )
    assert r.termination_reason is TerminationReason.CANCELLED
    assert r.iterations == 2
    assert r.feasible  # incumbent retained
    assert [e.iteration for e in seen] == [1, 2]
    assert all(e.has_feasible and e.best_objective is not None for e in seen)


def test_no_improvement_and_time_limit_stops():
    s = load_builtin("urban_grid")
    r = run(s, iterations=500, max_no_improvement=3)
    assert r.termination_reason is TerminationReason.NO_IMPROVEMENT
    r = run(s, iterations=100_000, time_limit_s=0.2)
    assert r.termination_reason is TerminationReason.TIME_LIMIT
