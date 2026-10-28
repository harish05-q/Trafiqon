"""Hybrid QPSO-inspired discrete optimizer. Formulation: docs/algorithms.md (steps 1-10).

Canonical QPSO position update on continuous random keys, combined with a problem-specific
decoder, feasibility repair, feasibility-preserving local search and Lamarckian write-back.
This is NOT canonical QPSO as a whole, and nothing here is quantum computation.
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
    ProgressEvent,
    Stopwatch,
    TerminationReason,
    check_number,
    finalize,
    merge_config,
)
from trafiqon.optimization.operators import local_search, repair
from trafiqon.optimization.problem import (
    Routes,
    RoutingProblem,
    cheapest_insertion,
    infeasibility_reasons,
)

UPDATE_RULES = ("qpso", "uniform_resample")
KEY_EPS = 1e-9

Fitness = tuple[bool, float]  # (infeasible, energy); lexicographic, lower is better


def decode(x: list[float], n: int, n_vehicles: int) -> Routes:
    """Step 2: vehicle = floor(assignment key), order = ascending order key (ties by index)."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_vehicles)]
    for k in range(n):
        v = min(math.floor(x[k]), n_vehicles - 1)
        buckets[max(v, 0)].append((x[n + k], k))
    return [[k for _, k in sorted(b)] for b in buckets]


def encode(routes: Routes, n: int) -> list[float]:
    """Exact inverse of `decode` for a complete assignment: decode(encode(S)) == S."""
    x = [0.0] * (2 * n)
    for v, seq in enumerate(routes):
        for rank, k in enumerate(seq):
            x[k] = v + 0.5
            x[n + k] = (rank + 0.5) / len(seq)
    return x


def qpso_update(
    x: list[float],
    pbest: list[float],
    gbest: list[float],
    mbest: list[float],
    beta: float,
    rng: random.Random,
) -> list[float]:
    """Step 6, per dimension: p = phi*pbest + (1-phi)*gbest;
    x' = p +/- beta * |mbest - x| * ln(1/u), u in (0, 1]."""
    out = []
    for d, xd in enumerate(x):
        phi = rng.random()
        p = phi * pbest[d] + (1.0 - phi) * gbest[d]
        u = 1.0 - rng.random()  # (0, 1]
        step = beta * abs(mbest[d] - xd) * math.log(1.0 / u)
        out.append(p + step if rng.random() < 0.5 else p - step)
    return out


def clip(x: list[float], n: int, n_vehicles: int) -> list[float]:
    upper = n_vehicles - KEY_EPS
    return [min(max(v, 0.0), upper) for v in x[:n]] + [min(max(v, 0.0), 1.0) for v in x[n:]]


class QpsoHybrid:
    id = "qpso_hybrid"
    uses_seed = True
    version = "1"
    defaults: Mapping[str, Any] = {
        "swarm_size": 20,
        "iterations": 100,
        "beta_start": 1.0,
        "beta_end": 0.5,
        "local_search_passes": 1,
        "lamarckian": True,
        "seed_with_construction": True,
        "overload_penalty": None,
        "time_limit_s": None,
        "max_no_improvement": None,
        "update_rule": "qpso",
    }

    def resolve_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        cfg = merge_config(self.defaults, config, self.id)
        check_number(cfg, "swarm_size", minimum=2, maximum=500, integer=True)
        check_number(cfg, "iterations", minimum=1, maximum=100_000, integer=True)
        check_number(cfg, "beta_start", minimum=0.0, maximum=3.0)
        check_number(cfg, "beta_end", minimum=0.0, maximum=3.0)
        check_number(cfg, "local_search_passes", minimum=0, maximum=100, integer=True)
        check_number(cfg, "overload_penalty", minimum=0, allow_none=True)
        check_number(cfg, "time_limit_s", minimum=0.001, maximum=3600, allow_none=True)
        check_number(cfg, "max_no_improvement", minimum=1, integer=True, allow_none=True)
        for key in ("lamarckian", "seed_with_construction"):
            if not isinstance(cfg[key], bool):
                raise ConfigError(f"{key} must be a boolean")
        if cfg["update_rule"] not in UPDATE_RULES:
            raise ConfigError(f"update_rule must be one of {list(UPDATE_RULES)}")
        return cfg

    def run(self, inp: AlgorithmInput) -> AlgorithmResult:
        clock = Stopwatch()
        cfg = self.resolve_config(inp.config)
        seed = inp.seed if inp.seed is not None else secrets.randbits(63)
        rng = random.Random(seed)
        matrix = inp.cost_matrix()
        problem = RoutingProblem(inp.scenario, matrix)
        n, n_veh = problem.n_customers, problem.n_vehicles

        def done(candidate, reason, **kw) -> AlgorithmResult:
            return finalize(
                self, inp, cfg, matrix, candidate, seed=seed, termination_reason=reason,
                elapsed_s=clock.elapsed(), **kw,
            )  # fmt: skip

        reasons = infeasibility_reasons(inp.scenario, matrix)
        if reasons:
            return done(
                None, TerminationReason.INFEASIBLE_SCENARIO, iterations=0, evaluations=0,
                time_to_first_feasible_s=None, diagnostics={"infeasibility": reasons},
            )  # fmt: skip

        penalty = cfg["overload_penalty"]
        if penalty is None:
            penalty = 2.0 * max(problem.max_leg_time, 1e-9)
        stats = {"evaluations": 0, "repairs_failed": 0, "ls_moves": 0}
        incumbent: dict[str, Any] = {"routes": None, "travel": math.inf, "first": None}

        def evaluate(x: list[float]) -> tuple[Fitness, list[float]]:
            """Decode, repair, local search, (write back). Returns fitness and new position."""
            routes, feasible = repair(problem, decode(x, n, n_veh))
            stats["evaluations"] += 1
            if feasible:
                if cfg["local_search_passes"]:
                    routes, moves = local_search(problem, routes, cfg["local_search_passes"])
                    stats["evaluations"] += moves
                    stats["ls_moves"] += moves
                travel = problem.total_cost(routes)
                fitness: Fitness = (False, travel)
                if travel < incumbent["travel"] - 1e-9:
                    incumbent["routes"] = [list(r) for r in routes]
                    incumbent["travel"] = travel
                    if incumbent["first"] is None:
                        incumbent["first"] = clock.elapsed()
            else:
                stats["repairs_failed"] += 1
                travel = problem.total_cost(routes)
                fitness = (True, travel + penalty * problem.overload(routes))
            return fitness, encode(routes, n) if cfg["lamarckian"] else x

        def stop_reason() -> TerminationReason | None:
            if inp.cancel.is_cancelled():
                return TerminationReason.CANCELLED
            if cfg["time_limit_s"] is not None and clock.elapsed() >= cfg["time_limit_s"]:
                return TerminationReason.TIME_LIMIT
            return None

        # Initial swarm.
        positions: list[list[float]] = []
        pbest: list[list[float]] = []
        pfit: list[Fitness] = []
        reason: TerminationReason | None = None
        for i in range(cfg["swarm_size"]):
            reason = stop_reason()
            if reason:
                break
            if i == 0 and cfg["seed_with_construction"]:
                x = encode(cheapest_insertion(problem), n)
            else:
                x = [rng.uniform(0, n_veh - KEY_EPS) for _ in range(n)]
                x += [rng.random() for _ in range(n)]
            fit, x = evaluate(x)
            positions.append(x)
            pbest.append(list(x))
            pfit.append(fit)

        history: list[HistoryPoint] = []
        diversity: list[float] = []
        iterations = 0
        since_improvement = 0

        def snapshot(it: int, current: float | None) -> None:
            best = incumbent["travel"] if incumbent["routes"] is not None else None
            history.append(HistoryPoint(it, stats["evaluations"], clock.elapsed(), current, best))

        if positions:
            g = min(range(len(pfit)), key=lambda i: (pfit[i], i))
            snapshot(0, None if pfit[g][0] else pfit[g][1])

        total = cfg["iterations"]
        while reason is None and iterations < total:
            if len(positions) < cfg["swarm_size"]:
                break  # initial swarm interrupted
            t = iterations
            beta = cfg["beta_start"] - (cfg["beta_start"] - cfg["beta_end"]) * (
                t / (total - 1) if total > 1 else 1.0
            )
            m = len(pbest)
            mbest = [sum(p[d] for p in pbest) / m for d in range(2 * n)]
            g = min(range(m), key=lambda i: (pfit[i], i))
            gbest = list(pbest[g])
            diversity.append(
                sum(abs(x[d] - mbest[d]) for x in positions for d in range(2 * n)) / (m * 2 * n)
            )
            before = incumbent["travel"]
            iter_best: Fitness | None = None
            for i in range(m):
                reason = stop_reason()
                if reason:
                    break
                if cfg["update_rule"] == "qpso":
                    x = qpso_update(positions[i], pbest[i], gbest, mbest, beta, rng)
                else:  # ablation baseline only (docs/algorithms.md)
                    x = [rng.uniform(0, n_veh) for _ in range(n)] + [rng.random() for _ in range(n)]
                fit, x = evaluate(clip(x, n, n_veh))
                positions[i] = x
                if fit < pfit[i]:
                    pbest[i], pfit[i] = list(x), fit
                if iter_best is None or fit < iter_best:
                    iter_best = fit
            if reason:
                break
            iterations += 1
            improved = incumbent["travel"] < before - 1e-9
            since_improvement = 0 if improved else since_improvement + 1
            current = None if iter_best is None or iter_best[0] else iter_best[1]
            snapshot(iterations, current)
            if inp.progress:
                inp.progress(
                    ProgressEvent(
                        iteration=iterations,
                        evaluations=stats["evaluations"],
                        elapsed_s=clock.elapsed(),
                        best_objective=incumbent["travel"] if incumbent["routes"] else None,
                        current_objective=current,
                        has_feasible=incumbent["routes"] is not None,
                        message=f"beta={beta:.3f} diversity={diversity[-1]:.4f}",
                    )
                )
            if (
                cfg["max_no_improvement"] is not None
                and since_improvement >= cfg["max_no_improvement"]
            ):
                reason = TerminationReason.NO_IMPROVEMENT

        if reason is None:
            reason = TerminationReason.ITERATION_LIMIT
        candidate = (
            problem.to_solution(incumbent["routes"]) if incumbent["routes"] is not None else None
        )
        if candidate is None and reason is not TerminationReason.CANCELLED:
            reason = TerminationReason.NO_SOLUTION_FOUND
        return done(
            candidate,
            reason,
            iterations=iterations,
            evaluations=stats["evaluations"],
            time_to_first_feasible_s=incumbent["first"],
            history=tuple(history),
            diagnostics={
                "update_rule": cfg["update_rule"],
                "particle_evaluations": iterations * cfg["swarm_size"] + len(pfit),
                "local_search_moves_evaluated": stats["ls_moves"],
                "repairs_failed": stats["repairs_failed"],
                "overload_penalty": penalty,
                "diversity": diversity,
                "internal_best_travel_time": incumbent["travel"]
                if incumbent["routes"] is not None
                else None,
                "note": "QPSO-inspired hybrid; canonical QPSO update on random keys only.",
            },
        )
