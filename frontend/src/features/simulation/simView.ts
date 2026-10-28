// Pure mapping from the backend's authoritative simulation state onto map inputs.
// Nothing here advances time or moves vehicles: positions come from the server.
import type { RouteOverlay } from "@/features/network/toFlow";
import type { ScenarioOut, SimulationState } from "@/lib/api/types";

/** Scenario with the simulation's current road conditions (closures, traffic, incidents). */
export function effectiveScenario(scenario: ScenarioOut, sim: SimulationState): ScenarioOut {
  if (!sim.road_overrides.length) return scenario;
  const byId = new Map(sim.road_overrides.map((o) => [o.edge_id, o]));
  return {
    ...scenario,
    graph: {
      ...scenario.graph,
      edges: scenario.graph.edges.map((e) => {
        const o = byId.get(e.id);
        return o
          ? {
              ...e,
              closed: o.closed,
              current_time: o.current_time,
              congestion: e.base_time > 0 ? o.current_time / e.base_time : e.congestion,
            }
          : e;
      }),
    },
  };
}

/** Remaining planned path per vehicle (current edge first), as route overlays. */
export function simRoutes(sim: SimulationState): RouteOverlay[] {
  return sim.vehicles
    .filter((v) => v.remaining_edge_ids.length > 0)
    .map((v) => ({ vehicleId: v.id, edgeIds: v.remaining_edge_ids }));
}

export interface VehicleMarker {
  id: string;
  x: number;
  y: number;
  status: SimulationState["vehicles"][number]["status"];
  label: string;
}

export function vehicleMarkers(sim: SimulationState): VehicleMarker[] {
  return sim.vehicles
    .filter((v) => v.x !== null && v.y !== null)
    .map((v) => ({
      id: v.id,
      x: v.x!,
      y: v.y!,
      status: v.status,
      label: `${v.id}: ${v.status.replace("_", " ")}, ${v.completed.length} stops done, ${v.remaining_stops.length} left`,
    }));
}

export function formatSimTime(min: number): string {
  const h = Math.floor(min / 60);
  const m = min - h * 60;
  return `${h}:${m.toFixed(1).padStart(4, "0")}`;
}
