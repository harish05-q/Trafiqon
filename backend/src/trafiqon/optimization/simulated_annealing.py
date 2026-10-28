"""Simulated Annealing baseline for the directed CVRP. See docs/algorithms.md.

State: one customer sequence per vehicle (`problem.Routes`).
Energy: E(S) = travel_time(S) + lambda * overload(S), where overload is total demand above
capacity. lambda (`overload_penalty`, minutes per demand unit) lets the search pass through
capacity-infeasible states; only overload-free states can become the reported incumbent.
Moves (uniformly chosen among enabled ones):
  relocate  - move one customer to any position of any route (incl. its own),
  swap      - exchange two customers (same or different routes),
  reverse   - reverse a subsequence of one route (re-costed in full: the graph is directed).
Moves that create an unreachable leg have infinite energy and are always rejected.
Acceptance: Metropolis, P = exp(-dE / T) for dE > 0.
Schedule: geometric, T_k = T0 * alpha^k. T0 defaults to -mean(dE+) / ln(p0) over sampled
moves from the initial state; alpha defaults to final_temperature_ratio^(1 / max_iterations).
Stops at: max_iterations, time_limit_s, T < T0 * final_temperature_ratio (explicit alpha only),
max_no_improvement, or cancellation.
"""

from __future__ import annotations

import math
import random
import secrets
from collections.abc import Mapping
from typing import Any

from trafiqon.optimization.contract import (
    AlgorithmInput,
    AlgorithmResult,
    ConfigError,
    HistoryPoint,
    ParamSpec,
    ProgressEvent,
    Stopwatch,
    TerminationReason,
    check_number,
    finalize,
    merge_config,
)
from trafiqon.optimization.problem import (
    Routes,
    RoutingProblem,
    cheapest_insertion,
    infeasibility_reasons,
)

MOVES = ("relocate", "swap", "reverse")


class _State:
    """Routes with cached per-route cost and load."""

    def __init__(self, problem: RoutingProblem, routes: Routes, penalty: float) -> None:
        self.p = problem
        self.penalty = penalty
        self.routes = [list(r) for r in routes]
        self.costs = [problem.route_cost(v, r)[0] for v, r in enumerate(self.routes)]
        self.loads = [problem.load(r) for r in self.routes]

    def over(self, v: int, load: int) -> int:
        return max(0, load - self.p.vehicles[v].capacity)

    def travel(self) -> float:
        return math.fsum(self.costs)

    def overload(self) -> int:
        return sum(self.over(v, load) for v, load in enumerate(self.loads))

    def energy(self) -> float:
        return self.travel() + self.penalty * self.overload()


class SimulatedAnnealing:
    id = "simulated_annealing"
    uses_seed = True
    version = "1"
    defaults: Mapping[str, Any] = {
        "max_iterations": 20_000,
        "time_limit_s": None,
        "initial_temperature": None,
        "initial_acceptance": 0.5,
        "temperature_samples": 100,
        "final_temperature_ratio": 1e-3,
        "cooling_rate": None,
        "max_no_improvement": None,
        "overload_penalty": None,
        "moves": list(MOVES),
        "progress_every": 500,
        "history_points": 200,
    }

    params = (
        ParamSpec(
            "max_iterations",
            "int",
            "Number of proposed moves (the main budget). Deterministic per seed.",
            1,
            10_000_000,
            unit="moves",
        ),
        ParamSpec(
            "time_limit_s",
            "float",
            "Optional wall-clock limit; makes results machine-dependent.",
            0.001,
            3600,
            nullable=True,
            null_meaning="none",
            unit="s",
        ),
        ParamSpec(
            "initial_temperature",
            "float",
            "Starting temperature T0 (minutes of travel time).",
            1e-9,
            None,
            nullable=True,
            null_meaning="auto: -mean(uphill delta) / ln(initial_acceptance)",
            advanced=True,
        ),
        ParamSpec(
            "initial_acceptance",
            "float",
            "Target probability of accepting an average uphill move at T0 (auto T0 only).",
            1e-6,
            0.999,
            advanced=True,
        ),
        ParamSpec(
            "temperature_samples",
            "int",
            "Random moves sampled to set the automatic T0.",
            1,
            10_000,
            advanced=True,
        ),
        ParamSpec(
            "final_temperature_ratio",
            "float",
            "T_final / T0. With automatic cooling the temperature reaches this fraction of T0 "
            "at max_iterations.",
            1e-12,
            0.999,
            advanced=True,
        ),
        ParamSpec(
            "cooling_rate",
            "float",
            "Geometric factor alpha in T_k = T0 * alpha^k. If set, the run also stops when "
            "T < T0 * final_temperature_ratio.",
            1e-6,
            0.999999999,
            nullable=True,
            null_meaning="auto: final_temperature_ratio^(1/max_iterations)",
            advanced=True,
        ),
        ParamSpec(
            "max_no_improvement",
            "int",
            "Stop after this many moves without a better feasible incumbent.",
            1,
            None,
            nullable=True,
            null_meaning="disabled",
        ),
        ParamSpec(
            "overload_penalty",
            "float",
            "Minutes added per unit of demand above capacity so the search can cross "
            "infeasible states. Never part of the reported objective.",
            0,
            None,
            nullable=True,
            null_meaning="auto: 2 x longest leg time",
            advanced=True,
        ),
        ParamSpec(
            "moves",
            "enum_list",
            "Neighbourhood moves chosen uniformly: relocate a customer, swap two customers, "
            "reverse a route segment.",
            choices=MOVES,
        ),
        ParamSpec(
            "progress_every",
            "int",
            "Report progress every N iterations.",
            1,
            None,
            advanced=True,
        ),
        ParamSpec(
            "history_points",
            "int",
            "Approximate number of convergence-history samples.",
            2,
            10_000,
            advanced=True,
        ),
    )

    def resolve_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        cfg = merge_config(self.defaults, config, self.id)
        check_number(cfg, "max_iterations", minimum=1, maximum=10_000_000, integer=True)
        check_number(cfg, "time_limit_s", minimum=0.001, maximum=3600, allow_none=True)
        check_number(cfg, "initial_temperature", minimum=1e-9, allow_none=True)
        check_number(cfg, "initial_acceptance", minimum=1e-6, maximum=0.999)
        check_number(cfg, "temperature_samples", minimum=1, maximum=10_000, integer=True)
        check_number(cfg, "final_temperature_ratio", minimum=1e-12, maximum=0.999)
        check_number(cfg, "cooling_rate", minimum=1e-6, maximum=0.999999999, allow_none=True)
        check_number(cfg, "max_no_improvement", minimum=1, integer=True, allow_none=True)
        check_number(cfg, "overload_penalty", minimum=0, allow_none=True)
        check_number(cfg, "progress_every", minimum=1, integer=True)
        check_number(cfg, "history_points", minimum=2, maximum=10_000, integer=True)
        moves = cfg["moves"]
        if not isinstance(moves, list | tuple) or not moves or set(moves) - set(MOVES):
            raise ConfigError(f"moves must be a non-empty subset of {list(MOVES)}")
        cfg["moves"] = list(dict.fromkeys(moves))
        return cfg

    def run(self, inp: AlgorithmInput) -> AlgorithmResult:
        clock = Stopwatch()
        cfg = self.resolve_config(inp.config)
        seed = inp.seed if inp.seed is not None else secrets.randbits(63)
        rng = random.Random(seed)
        matrix = inp.cost_matrix()
        problem = RoutingProblem(inp.scenario, matrix)

        def done(candidate, reason, **kw) -> AlgorithmResult:
            return finalize(
                self,
                inp,
                cfg,
                matrix,
                candidate,
                seed=seed,
                termination_reason=reason,
                elapsed_s=clock.elapsed(),
                **kw,
            )

        reasons = infeasibility_reasons(inp.scenario, matrix)
        if reasons:
            return done(
                None,
                TerminationReason.INFEASIBLE_SCENARIO,
                iterations=0,
                evaluations=0,
                time_to_first_feasible_s=None,
                diagnostics={"infeasibility": reasons},
            )

        penalty = cfg["overload_penalty"]
        if penalty is None:
            penalty = 2.0 * max(problem.max_leg_time, 1e-9)
        state = _State(problem, cheapest_insertion(problem), penalty)
        evaluations = 1
        energy = state.energy()

        best_routes: Routes | None = None
        best_travel = math.inf
        first_feasible: float | None = None
        if state.overload() == 0:
            best_routes, best_travel = [list(r) for r in state.routes], state.travel()
            first_feasible = clock.elapsed()

        moves = cfg["moves"]
        t0 = cfg["initial_temperature"]
        if t0 is None:
            deltas = []
            for _ in range(cfg["temperature_samples"]):
                proposal = self._propose(state, rng, rng.choice(moves))
                evaluations += 1
                if proposal is not None and math.isfinite(proposal[0]) and proposal[0] > 0:
                    deltas.append(proposal[0])
            mean_up = math.fsum(deltas) / len(deltas) if deltas else 1.0
            t0 = -mean_up / math.log(cfg["initial_acceptance"])
        max_it = cfg["max_iterations"]
        alpha = cfg["cooling_rate"]
        explicit_alpha = alpha is not None
        if alpha is None:
            alpha = cfg["final_temperature_ratio"] ** (1.0 / max_it)
        t_min = t0 * cfg["final_temperature_ratio"]

        history: list[HistoryPoint] = [
            HistoryPoint(
                0,
                evaluations,
                clock.elapsed(),
                state.travel(),
                None if best_routes is None else best_travel,
            )
        ]
        record_every = max(1, max_it // cfg["history_points"])
        accepted = improved_count = since_improvement = 0
        temperature = t0
        reason = TerminationReason.ITERATION_LIMIT
        iteration = 0
        for iteration in range(1, max_it + 1):
            if iteration % 64 == 0 or iteration == 1:
                if inp.cancel.is_cancelled():
                    reason = TerminationReason.CANCELLED
                    iteration -= 1
                    break
                if cfg["time_limit_s"] is not None and clock.elapsed() >= cfg["time_limit_s"]:
                    reason = TerminationReason.TIME_LIMIT
                    iteration -= 1
                    break

            proposal = self._propose(state, rng, rng.choice(moves))
            evaluations += 1
            if proposal is not None and math.isfinite(proposal[0]):
                delta, apply = proposal
                if delta <= 0 or rng.random() < math.exp(-delta / temperature):
                    apply()
                    accepted += 1
                    energy += delta
                    if state.overload() == 0:
                        travel = state.travel()
                        if travel < best_travel - 1e-9:
                            best_routes, best_travel = [list(r) for r in state.routes], travel
                            improved_count += 1
                            since_improvement = -1
                            if first_feasible is None:
                                first_feasible = clock.elapsed()
                            history.append(
                                HistoryPoint(
                                    iteration, evaluations, clock.elapsed(), travel, best_travel
                                )
                            )
            since_improvement += 1
            temperature *= alpha

            if iteration % record_every == 0:
                history.append(
                    HistoryPoint(
                        iteration,
                        evaluations,
                        clock.elapsed(),
                        state.travel(),
                        None if best_routes is None else best_travel,
                    )
                )
            if inp.progress and iteration % cfg["progress_every"] == 0:
                inp.progress(
                    ProgressEvent(
                        iteration=iteration,
                        evaluations=evaluations,
                        elapsed_s=clock.elapsed(),
                        best_objective=None if best_routes is None else best_travel,
                        current_objective=state.travel(),
                        has_feasible=best_routes is not None,
                        message=f"T={temperature:.4g}",
                    )
                )
            if explicit_alpha and temperature < t_min:
                reason = TerminationReason.MIN_TEMPERATURE
                break
            if (
                cfg["max_no_improvement"] is not None
                and since_improvement >= cfg["max_no_improvement"]
            ):
                reason = TerminationReason.NO_IMPROVEMENT
                break

        candidate = problem.to_solution(best_routes) if best_routes is not None else None
        return done(
            candidate,
            reason
            if candidate is not None or reason is TerminationReason.CANCELLED
            else TerminationReason.NO_SOLUTION_FOUND,
            iterations=iteration,
            evaluations=evaluations,
            time_to_first_feasible_s=first_feasible,
            history=tuple(history),
            diagnostics={
                "initial_temperature": t0,
                "cooling_rate": alpha,
                "final_temperature": temperature,
                "overload_penalty": penalty,
                "accepted_moves": accepted,
                "acceptance_rate": accepted / iteration if iteration else 0.0,
                "incumbent_improvements": improved_count,
                "final_state_overload": state.overload(),
                "internal_best_travel_time": None if best_routes is None else best_travel,
                "energy_drift_check": abs(energy - state.energy()),
            },
        )

    # --- moves: return (delta_energy, apply) or None if not applicable -------------------

    def _propose(self, s: _State, rng: random.Random, move: str):
        if move == "relocate":
            return self._relocate(s, rng)
        if move == "swap":
            return self._swap(s, rng)
        return self._reverse(s, rng)

    @staticmethod
    def _pick_position(s: _State, rng: random.Random) -> tuple[int, int] | None:
        nonempty = [v for v, r in enumerate(s.routes) if r]
        if not nonempty:
            return None
        # Uniform over customers, not over routes.
        k = rng.randrange(sum(len(s.routes[v]) for v in nonempty))
        for v in nonempty:
            if k < len(s.routes[v]):
                return v, k
            k -= len(s.routes[v])
        raise AssertionError("unreachable")

    def _change(self, s: _State, new: dict[int, list[int]]):
        """Delta energy for replacing the given routes, and a closure that applies it."""
        p = s.p
        delta = 0.0
        updates = []
        for v, seq in new.items():
            cost = p.route_cost(v, seq)[0]
            if not math.isfinite(cost):
                return math.inf, lambda: None
            load = p.load(seq)
            delta += (cost - s.costs[v]) + s.penalty * (s.over(v, load) - s.over(v, s.loads[v]))
            updates.append((v, seq, cost, load))

        def apply() -> None:
            for v, seq, cost, load in updates:
                s.routes[v], s.costs[v], s.loads[v] = seq, cost, load

        return delta, apply

    def _relocate(self, s: _State, rng: random.Random):
        pos = self._pick_position(s, rng)
        if pos is None:
            return None
        v1, i = pos
        c = s.routes[v1][i]
        v2 = rng.randrange(s.p.n_vehicles)
        src = s.routes[v1][:i] + s.routes[v1][i + 1 :]
        if v2 == v1:
            if len(src) == 0:
                return None
            j = rng.randrange(len(src) + 1)
            if j == i:
                return None
            return self._change(s, {v1: [*src[:j], c, *src[j:]]})
        dst = s.routes[v2]
        j = rng.randrange(len(dst) + 1)
        return self._change(s, {v1: src, v2: [*dst[:j], c, *dst[j:]]})

    def _swap(self, s: _State, rng: random.Random):
        a, b = self._pick_position(s, rng), self._pick_position(s, rng)
        if a is None or b is None or a == b:
            return None
        (v1, i), (v2, j) = a, b
        if v1 == v2:
            seq = list(s.routes[v1])
            seq[i], seq[j] = seq[j], seq[i]
            return self._change(s, {v1: seq})
        r1, r2 = list(s.routes[v1]), list(s.routes[v2])
        r1[i], r2[j] = s.routes[v2][j], s.routes[v1][i]
        return self._change(s, {v1: r1, v2: r2})

    def _reverse(self, s: _State, rng: random.Random):
        candidates = [v for v, r in enumerate(s.routes) if len(r) >= 2]
        if not candidates:
            return None
        v = rng.choice(candidates)
        seq = s.routes[v]
        i, j = sorted(rng.sample(range(len(seq)), 2))
        return self._change(s, {v: seq[:i] + seq[i : j + 1][::-1] + seq[j + 1 :]})
