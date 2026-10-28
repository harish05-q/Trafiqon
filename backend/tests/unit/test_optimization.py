import math
import random

import pytest
from helpers import edge, graph, line_scenario

from trafiqon.domain import Customer, Depot, Scenario, Vehicle
from trafiqon.fixtures import BUILTIN_SCENARIOS, load_builtin
from trafiqon.optimization import (
    ALGORITHMS,
    AlgorithmInput,
    CancelFlag,
    ConfigError,
    Optimality,
    OrToolsCvrp,
    SimulatedAnnealing,
    TerminationReason,
    get_algorithm,
)
from trafiqon.optimization.problem import RoutingProblem, cheapest_insertion, infeasibility_reasons
from trafiqon.routing import build_scenario_matrix, evaluate_solution

FAST = {
    "ortools_cvrp": {"time_limit_s": 0.3},
    "simulated_annealing": {"max_iterations": 3000},
}
FIXTURES = sorted(BUILTIN_SCENARIOS)


def run(algorithm_id, scenario, seed=0, **cfg):
    return get_algorithm(algorithm_id).run(
        AlgorithmInput(scenario, {**FAST[algorithm_id], **cfg}, seed=seed)
    )


def two_islands() -> Scenario:
    """Two disconnected components, each with its own depot, vehicle and customers."""
    g = graph(
        ["p", "a1", "a2", "q", "b1"],
        [
            edge("p", "a1", 1),
            edge("a1", "a2", 1),
            edge("a2", "p", 1),
            edge("a1", "p", 5),
            edge("q", "b1", 2),
            edge("b1", "q", 2),
        ],
    )
    return Scenario(
        id="islands",
        name="islands",
        graph=g,
        depots=(Depot("P", "p"), Depot("Q", "q")),
        customers=(Customer("A1", "a1", 1), Customer("A2", "a2", 1), Customer("B1", "b1", 1)),
        vehicles=(Vehicle("vq", 5, "Q"), Vehicle("vp", 5, "P")),
    )


# --- shared representation ---------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", FIXTURES)
def test_internal_cost_matches_shared_evaluator(scenario_id):
    s = load_builtin(scenario_id)
    m = build_scenario_matrix(s)
    p = RoutingProblem(s, m)
    rng = random.Random(5)
    for _ in range(50):
        order = list(range(p.n_customers))
        rng.shuffle(order)
        routes = [[] for _ in range(p.n_vehicles)]
        for c in order:
            routes[rng.randrange(p.n_vehicles)].append(c)
        result = evaluate_solution(s, p.to_solution(routes), m)
        assert result.objective == pytest.approx(p.total_cost(routes))
        capacity_ok = not any(v.code == "capacity_exceeded" for v in result.violations)
        assert capacity_ok == (p.overload(routes) == 0)


@pytest.mark.parametrize("scenario_id", FIXTURES)
def test_cheapest_insertion_is_complete_and_feasible_on_fixtures(scenario_id):
    s = load_builtin(scenario_id)
    p = RoutingProblem(s, build_scenario_matrix(s))
    routes = cheapest_insertion(p)
    assert sorted(c for r in routes for c in r) == list(range(p.n_customers))
    assert p.overload(routes) == 0
    assert evaluate_solution(s, p.to_solution(routes)).feasible


def test_infeasibility_reasons():
    assert infeasibility_reasons(line_scenario(), build_scenario_matrix(line_scenario())) == []
    tight = line_scenario(capacity=3, demands=(3, 4))
    codes = {r["code"] for r in infeasibility_reasons(tight, build_scenario_matrix(tight))}
    assert codes == {"demand_exceeds_capacity", "insufficient_fleet_capacity"}
    s = line_scenario()
    cut = s.with_graph(s.graph.with_edge_closed("b->a"))
    codes = {r["code"] for r in infeasibility_reasons(cut, build_scenario_matrix(cut))}
    assert codes == {"customer_unreachable"}


# --- common contract ---------------------------------------------------------------------


def test_registry():
    assert set(ALGORITHMS) == {"ortools_cvrp", "simulated_annealing"}
    with pytest.raises(ConfigError):
        get_algorithm("random_search")


@pytest.mark.parametrize(
    ("algorithm", "config"),
    [
        (OrToolsCvrp(), {"nope": 1}),
        (OrToolsCvrp(), {"time_limit_s": 0}),
        (OrToolsCvrp(), {"time_limit_s": "fast"}),
        (OrToolsCvrp(), {"local_search_metaheuristic": "MAGIC"}),
        (OrToolsCvrp(), {"first_solution_strategy": "NOPE"}),
        (SimulatedAnnealing(), {"max_iterations": 0}),
        (SimulatedAnnealing(), {"max_iterations": 1.5}),
        (SimulatedAnnealing(), {"moves": ["teleport"]}),
        (SimulatedAnnealing(), {"moves": []}),
        (SimulatedAnnealing(), {"initial_acceptance": 1.0}),
        (SimulatedAnnealing(), {"cooling_rate": 1.0}),
        (SimulatedAnnealing(), {"max_iterations": True}),
    ],
)
def test_invalid_config_rejected(algorithm, config):
    with pytest.raises(ConfigError):
        algorithm.resolve_config(config)


@pytest.mark.parametrize("algorithm_id", sorted(FAST))
@pytest.mark.parametrize("scenario_id", FIXTURES)
def test_result_is_scored_by_shared_evaluator(algorithm_id, scenario_id):
    s = load_builtin(scenario_id)
    r = run(algorithm_id, s)
    assert r.feasible
    assert r.solution is not None and r.evaluation is not None
    independent = evaluate_solution(s, r.solution)
    assert independent.feasible
    assert r.objective == independent.objective
    assert r.optimality is Optimality.NOT_PROVEN
    assert r.time_to_first_feasible_s is not None
    assert 0 <= r.time_to_first_feasible_s <= r.elapsed_s
    bests = [h.best_objective for h in r.history if h.best_objective is not None]
    assert bests == sorted(bests, reverse=True)  # best-so-far never gets worse
    assert r.config == get_algorithm(algorithm_id).resolve_config(FAST[algorithm_id])


@pytest.mark.parametrize("algorithm_id", sorted(FAST))
def test_disconnected_components_and_unreachable_pairs(algorithm_id):
    s = two_islands()
    m = build_scenario_matrix(s)
    assert m.unreachable_pairs()  # a1->b1 etc. are unreachable
    r = run(algorithm_id, s)
    assert r.feasible, r.diagnostics
    by_vehicle = {route.vehicle_id: set(route.customer_ids) for route in r.solution.routes}
    assert by_vehicle == {"vp": {"A1", "A2"}, "vq": {"B1"}}
    # p->a1->a2->p (3) + q->b1->q (4)
    assert r.objective == pytest.approx(7.0)


@pytest.mark.parametrize("algorithm_id", sorted(FAST))
def test_multiple_allowed_end_depots(algorithm_id):
    # Vehicle may end at P or Q; returning to Q from b is much cheaper.
    g = graph(
        ["p", "b", "q"],
        [edge("p", "b", 1), edge("b", "p", 10), edge("b", "q", 1), edge("q", "p", 1)],
    )
    s = Scenario(
        id="ends",
        name="ends",
        graph=g,
        depots=(Depot("P", "p"), Depot("Q", "q")),
        customers=(Customer("B", "b", 1),),
        vehicles=(Vehicle("v", 5, "P", ("P", "Q")),),
    )
    r = run(algorithm_id, s)
    assert r.feasible
    assert r.solution.routes[0].end_depot_id == "Q"
    assert r.objective == pytest.approx(2.0)


@pytest.mark.parametrize("algorithm_id", sorted(FAST))
@pytest.mark.parametrize(
    "make",
    [
        lambda: line_scenario(capacity=3, demands=(3, 4)),
        lambda: (lambda s: s.with_graph(s.graph.with_edge_closed("b->a")))(line_scenario()),
    ],
    ids=["capacity", "unreachable"],
)
def test_infeasible_scenario_reported_not_hidden(algorithm_id, make):
    r = run(algorithm_id, make())
    assert not r.feasible
    assert r.solution is None and r.objective is None and r.evaluation is None
    assert r.termination_reason is TerminationReason.INFEASIBLE_SCENARIO
    assert r.diagnostics["infeasibility"]


# --- Simulated Annealing ------------------------------------------------------------------


def test_sa_is_deterministic_for_a_seed():
    s = load_builtin("congested_city")
    a, b = run("simulated_annealing", s, seed=42), run("simulated_annealing", s, seed=42)
    assert a.solution == b.solution
    assert a.objective == b.objective
    assert [(h.iteration, h.best_objective) for h in a.history] == [
        (h.iteration, h.best_objective) for h in b.history
    ]
    assert a.diagnostics["accepted_moves"] == b.diagnostics["accepted_moves"]


def test_sa_records_generated_seed_and_reproduces_it():
    s = load_builtin("urban_grid")
    first = run("simulated_annealing", s, seed=None)
    assert isinstance(first.seed, int)
    again = run("simulated_annealing", s, seed=first.seed)
    assert again.objective == first.objective and again.solution == first.solution


def test_sa_explores_capacity_infeasible_states_but_reports_only_feasible():
    # Tight capacity: 3 vehicles x 10 for 8 customers of total demand 26.
    s = load_builtin("incident_response")
    r = run("simulated_annealing", s, seed=3, overload_penalty=0.01, max_iterations=4000)
    assert r.feasible
    assert evaluate_solution(s, r.solution).feasible
    assert all(route.customer_ids for route in r.solution.routes)


def test_sa_internal_energy_bookkeeping_is_consistent():
    r = run("simulated_annealing", load_builtin("urban_grid"), seed=1)
    assert r.diagnostics["energy_drift_check"] < 1e-6
    assert r.diagnostics["internal_best_travel_time"] == pytest.approx(r.objective)


def test_sa_improves_on_its_construction_on_congested_city():
    s = load_builtin("congested_city")
    p = RoutingProblem(s, build_scenario_matrix(s))
    constructed = p.total_cost(cheapest_insertion(p))
    r = run("simulated_annealing", s, seed=0, max_iterations=20_000)
    assert r.objective <= constructed + 1e-9
    assert r.diagnostics["acceptance_rate"] > 0


def test_sa_cancellation_before_and_during_run():
    s = load_builtin("urban_grid")
    pre = CancelFlag()
    pre.cancel()
    r = SimulatedAnnealing().run(AlgorithmInput(s, {"max_iterations": 10_000}, seed=0, cancel=pre))
    assert r.termination_reason is TerminationReason.CANCELLED
    assert r.iterations == 0
    assert r.feasible  # the constructed incumbent is retained, not discarded

    flag, events = CancelFlag(), []

    def progress(e):
        events.append(e)
        flag.cancel()

    r = SimulatedAnnealing().run(
        AlgorithmInput(
            s,
            {"max_iterations": 100_000, "progress_every": 100},
            seed=0,
            progress=progress,
            cancel=flag,
        )
    )
    assert r.termination_reason is TerminationReason.CANCELLED
    assert 100 <= r.iterations < 300
    assert r.feasible and r.objective is not None
    assert events[0].iteration == 100 and events[0].evaluations is not None


def test_sa_other_stopping_rules():
    s = load_builtin("urban_grid")
    r = run("simulated_annealing", s, cooling_rate=0.9, max_iterations=100_000)
    assert r.termination_reason is TerminationReason.MIN_TEMPERATURE
    assert r.iterations < 100_000
    r = run("simulated_annealing", s, max_no_improvement=50, max_iterations=100_000)
    assert r.termination_reason is TerminationReason.NO_IMPROVEMENT
    r = run("simulated_annealing", s, time_limit_s=0.05, max_iterations=10_000_000)
    assert r.termination_reason is TerminationReason.TIME_LIMIT


@pytest.mark.parametrize("move", ["relocate", "swap", "reverse"])
def test_sa_each_move_alone_keeps_results_feasible(move):
    s = load_builtin("congested_city")
    r = run("simulated_annealing", s, moves=[move], max_iterations=2000)
    assert r.feasible
    assert r.config["moves"] == [move]


# --- OR-Tools -----------------------------------------------------------------------------


def test_ortools_reports_status_and_never_claims_optimality_on_time_limit():
    r = run("ortools_cvrp", load_builtin("congested_city"))
    assert r.diagnostics["solver_status"].startswith("ROUTING_")
    assert r.seed is None and r.evaluations is None
    if r.termination_reason is TerminationReason.TIME_LIMIT:
        assert r.optimality is Optimality.NOT_PROVEN
    assert r.diagnostics["solutions_found"] == r.iterations >= 1


def test_ortools_removes_unreachable_arcs():
    r = run("ortools_cvrp", two_islands())
    assert r.diagnostics["removed_unreachable_arcs"] > 0


def test_ortools_cancellation_stops_search_early():
    flag = CancelFlag()
    r = OrToolsCvrp().run(
        AlgorithmInput(
            load_builtin("congested_city"),
            {"time_limit_s": 20},
            cancel=flag,
            progress=lambda e: flag.cancel(),
        )
    )
    assert r.termination_reason is TerminationReason.CANCELLED
    assert r.elapsed_s < 5
    assert r.feasible  # first solution found before the cancel is kept


def test_ortools_is_at_least_as_good_as_insertion_on_fixtures():
    for scenario_id in FIXTURES:
        s = load_builtin(scenario_id)
        p = RoutingProblem(s, build_scenario_matrix(s))
        constructed = p.total_cost(cheapest_insertion(p))
        r = run("ortools_cvrp", s, time_limit_s=0.5)
        assert r.objective <= constructed + 1e-6 or math.isclose(r.objective, constructed)
