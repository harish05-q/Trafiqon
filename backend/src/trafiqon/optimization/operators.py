"""Feasibility repair and feasibility-preserving local search on the shared representation.

See docs/algorithms.md, QPSO steps 3 and 8. All functions are deterministic.
"""

from __future__ import annotations

import itertools
import math

from trafiqon.optimization.problem import Routes, RoutingProblem

EPS = 1e-9


def unreachable_legs(problem: RoutingProblem, v: int, seq: list[int]) -> int:
    """Number of unreachable legs on vehicle v's route (the end leg counts if no allowed end
    depot is reachable)."""
    if not seq:
        return 0
    t, loc, spec = problem.t, problem.loc, problem.vehicles[v]
    bad = int(math.isinf(t[spec.start][loc[seq[0]]]))
    for a, b in itertools.pairwise(seq):
        bad += int(math.isinf(t[loc[a]][loc[b]]))
    row = t[loc[seq[-1]]]
    bad += int(all(math.isinf(row[idx]) for _, idx in spec.ends))
    return bad


def best_insertion(
    problem: RoutingProblem,
    routes: Routes,
    costs: list[float],
    loads: list[int],
    c: int,
    *,
    respect_capacity: bool = True,
) -> tuple[int, int, float] | None:
    """Cheapest (vehicle, position, new route cost) inserting customer c with every leg
    reachable and, if `respect_capacity`, within capacity. Without capacity, positions are
    ranked by (resulting overload, cost increase). Ties go to the lower vehicle/position."""
    demand = problem.dem[c]
    best_key: tuple[float, float, int, int] | None = None
    best_cost = math.inf
    for v, seq in enumerate(routes):
        over = max(0, loads[v] + demand - problem.vehicles[v].capacity)
        if respect_capacity and over > 0:
            continue
        for pos in range(len(seq) + 1):
            cost = problem.route_cost(v, [*seq[:pos], c, *seq[pos:]])[0]
            if math.isinf(cost):
                continue
            key = (over if not respect_capacity else 0, cost - costs[v], v, pos)
            if best_key is None or key < best_key:
                best_key, best_cost = key, cost
    if best_key is None:
        return None
    return best_key[2], best_key[3], best_cost


def repair(problem: RoutingProblem, routes: Routes) -> tuple[Routes, bool]:
    """Make `routes` capacity-feasible with all legs reachable, if possible.

    Returns (routes, feasible). Every customer stays assigned exactly once. If a customer
    cannot be placed feasibly it is put where overload is smallest; if it cannot be placed
    on any reachable position it is appended to vehicle 0 (route then has inf cost).
    """
    routes = [list(r) for r in routes]
    removed: list[int] = []
    for v, seq in enumerate(routes):
        # a. unreachable legs: remove the customer whose removal fixes the most legs.
        while unreachable_legs(problem, v, seq):
            current = unreachable_legs(problem, v, seq)
            best = None
            for i in range(len(seq)):
                rest = seq[:i] + seq[i + 1 :]
                gain = current - unreachable_legs(problem, v, rest)
                cost = problem.route_cost(v, rest)[0]
                key = (-gain, cost, i)
                if best is None or key < best:
                    best = key
            removed.append(seq.pop(best[2]))  # type: ignore[index]
        # b. capacity: remove the customer whose removal saves the most travel time.
        cap = problem.vehicles[v].capacity
        while problem.load(seq) > cap:
            full = problem.route_cost(v, seq)[0]
            best = None
            for i in range(len(seq)):
                saving = full - problem.route_cost(v, seq[:i] + seq[i + 1 :])[0]
                key = (-saving, i)
                if best is None or key < best:
                    best = key
            removed.append(seq.pop(best[1]))  # type: ignore[index]

    costs = [problem.route_cost(v, r)[0] for v, r in enumerate(routes)]
    loads = [problem.load(r) for r in routes]
    feasible = True
    for c in sorted(removed, key=lambda c: (-problem.dem[c], c)):
        choice = best_insertion(problem, routes, costs, loads, c)
        if choice is None:
            feasible = False
            choice = best_insertion(problem, routes, costs, loads, c, respect_capacity=False)
        if choice is None:
            routes[0].append(c)
            costs[0] = problem.route_cost(0, routes[0])[0]
            loads[0] += problem.dem[c]
            continue
        v, pos, cost = choice
        routes[v].insert(pos, c)
        costs[v], loads[v] = cost, loads[v] + problem.dem[c]
    if feasible:
        feasible = problem.overload(routes) == 0 and all(math.isfinite(c) for c in costs)
    return routes, feasible


class _LS:
    def __init__(self, problem: RoutingProblem, routes: Routes) -> None:
        self.p = problem
        self.routes = [list(r) for r in routes]
        self.costs = [problem.route_cost(v, r)[0] for v, r in enumerate(self.routes)]
        self.loads = [problem.load(r) for r in self.routes]
        self.evaluations = 0

    def _accept(self, new: dict[int, list[int]]) -> bool:
        """Apply `new` routes if all are within capacity, reachable, and total cost drops."""
        self.evaluations += 1
        p = self.p
        delta = 0.0
        staged = []
        for v, seq in new.items():
            load = p.load(seq)
            if load > p.vehicles[v].capacity:
                return False
            cost = p.route_cost(v, seq)[0]
            if math.isinf(cost):
                return False
            delta += cost - self.costs[v]
            staged.append((v, seq, cost, load))
        if delta >= -EPS:
            return False
        for v, seq, cost, load in staged:
            self.routes[v], self.costs[v], self.loads[v] = seq, cost, load
        return True

    def relocate(self) -> bool:
        routes = self.routes
        for v1, r1 in enumerate(routes):
            for i, c in enumerate(r1):
                src = r1[:i] + r1[i + 1 :]
                for v2, r2 in enumerate(routes):
                    if v2 == v1:
                        for j in range(len(src) + 1):
                            if j != i and self._accept({v1: [*src[:j], c, *src[j:]]}):
                                return True
                        continue
                    if self.loads[v2] + self.p.dem[c] > self.p.vehicles[v2].capacity:
                        continue
                    for j in range(len(r2) + 1):
                        if self._accept({v1: src, v2: [*r2[:j], c, *r2[j:]]}):
                            return True
        return False

    def swap(self) -> bool:
        routes = self.routes
        positions = [(v, i) for v, r in enumerate(routes) for i in range(len(r))]
        for a in range(len(positions)):
            v1, i = positions[a]
            for b in range(a + 1, len(positions)):
                v2, j = positions[b]
                if v1 == v2:
                    seq = list(routes[v1])
                    seq[i], seq[j] = seq[j], seq[i]
                    if self._accept({v1: seq}):
                        return True
                else:
                    r1, r2 = list(routes[v1]), list(routes[v2])
                    r1[i], r2[j] = routes[v2][j], routes[v1][i]
                    if self._accept({v1: r1, v2: r2}):
                        return True
        return False

    def two_opt(self) -> bool:
        for v, seq in enumerate(self.routes):
            for i in range(len(seq) - 1):
                for j in range(i + 1, len(seq)):
                    if self._accept({v: seq[:i] + seq[i : j + 1][::-1] + seq[j + 1 :]}):
                        return True
        return False


def local_search(problem: RoutingProblem, routes: Routes, passes: int) -> tuple[Routes, int]:
    """First-improvement descent with relocate, swap and 2-opt reversal.

    Input routes must be feasible; every applied move keeps them feasible and strictly
    lowers travel time. A pass applies each operator repeatedly until it finds no improving
    move; stops early when a whole pass improves nothing. Returns (routes, moves evaluated).
    """
    ls = _LS(problem, routes)
    for _ in range(passes):
        improved = False
        for op in (ls.relocate, ls.swap, ls.two_opt):
            while op():
                improved = True
        if not improved:
            break
    return ls.routes, ls.evaluations
