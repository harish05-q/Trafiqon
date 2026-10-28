"""Candidate CVRP solution representation shared by every algorithm."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VehicleRoute:
    """Ordered customer visits for one vehicle, from `start_depot_id` to `end_depot_id`.

    `legs`, when given, are explicit edge-id paths for each consecutive stop pair
    (len(customer_ids) + 1 legs). When omitted, the evaluator uses shortest paths
    under the scenario's current conditions.
    """

    vehicle_id: str
    customer_ids: tuple[str, ...]
    start_depot_id: str
    end_depot_id: str
    legs: tuple[tuple[str, ...], ...] | None = None


@dataclass(frozen=True, slots=True)
class Solution:
    routes: tuple[VehicleRoute, ...]
