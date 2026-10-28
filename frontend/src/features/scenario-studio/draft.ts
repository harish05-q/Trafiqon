// Scenario Studio draft: a pure reducer over ScenarioData. Every edit either produces a
// structurally sound draft or is rejected with a readable `error` (state otherwise unchanged).
// The server's /scenarios/validate and save endpoints remain the authority.
import type { EdgeOut, ScenarioData } from "@/lib/api/types";

export interface Draft {
  data: ScenarioData;
  dirty: boolean;
  error: string | null;
}

export type EdgePatch = Partial<
  Pick<EdgeOut, "distance" | "base_time" | "current_time" | "closed" | "road_class">
>;

export type DraftAction =
  | { type: "load"; data: ScenarioData }
  | { type: "addNode"; x: number; y: number }
  | { type: "moveNode"; id: string; x: number; y: number }
  | { type: "deleteNode"; id: string }
  | { type: "addEdge"; source: string; target: string }
  | { type: "updateEdge"; id: string; patch: EdgePatch }
  | { type: "deleteEdge"; id: string }
  | { type: "setRole"; nodeId: string; role: "intersection" | "depot" | "customer" }
  | { type: "setDemand"; customerId: string; demand: number }
  | { type: "addVehicle" }
  | { type: "updateVehicle"; id: string; capacity?: number; startDepotId?: string }
  | { type: "deleteVehicle"; id: string }
  | { type: "markSaved" }
  | { type: "clearError" };

/** Default speed for new roads (km/h): base_time = distance / speed. */
export const NEW_ROAD_KMH = 30;

export const emptyScenario = (): ScenarioData => ({
  description: "",
  synthetic: true,
  settings: { units: { time: "min", distance: "km" } },
  graph: { nodes: [], edges: [] },
  depots: [],
  customers: [],
  vehicles: [],
});

export const initialDraft = (data: ScenarioData = emptyScenario()): Draft => ({
  data,
  dirty: false,
  error: null,
});

function nextId(prefix: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  let k = 1;
  while (used.has(`${prefix}${k}`)) k++;
  return `${prefix}${k}`;
}

const round = (v: number, digits = 3) => Math.round(v * 10 ** digits) / 10 ** digits;

function edit(state: Draft, data: ScenarioData): Draft {
  return { data, dirty: true, error: null };
}

function reject(state: Draft, error: string): Draft {
  return { ...state, error };
}

function finiteNonNegative(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && v >= 0;
}

export function draftReducer(state: Draft, action: DraftAction): Draft {
  const d = state.data;
  const nodes = d.graph.nodes;
  const edges = d.graph.edges;
  switch (action.type) {
    case "load":
      return initialDraft(action.data);
    case "markSaved":
      return { ...state, dirty: false, error: null };
    case "clearError":
      return { ...state, error: null };

    case "addNode": {
      if (!Number.isFinite(action.x) || !Number.isFinite(action.y))
        return reject(state, "Node coordinates must be finite numbers.");
      const id = nextId(
        "n",
        nodes.map((n) => n.id),
      );
      return edit(state, {
        ...d,
        graph: {
          ...d.graph,
          nodes: [...nodes, { id, x: round(action.x, 2), y: round(action.y, 2), label: null }],
        },
      });
    }

    case "moveNode": {
      if (!nodes.some((n) => n.id === action.id))
        return reject(state, `Unknown node ${action.id}.`);
      if (!Number.isFinite(action.x) || !Number.isFinite(action.y))
        return reject(state, "Node coordinates must be finite numbers.");
      return edit(state, {
        ...d,
        graph: {
          ...d.graph,
          nodes: nodes.map((n) =>
            n.id === action.id ? { ...n, x: round(action.x, 2), y: round(action.y, 2) } : n,
          ),
        },
      });
    }

    case "deleteNode": {
      if (!nodes.some((n) => n.id === action.id))
        return reject(state, `Unknown node ${action.id}.`);
      const depots = d.depots.filter((x) => x.node_id === action.id).map((x) => x.id);
      const users = d.vehicles.filter(
        (v) => depots.includes(v.start_depot_id) || v.end_depot_ids.some((e) => depots.includes(e)),
      );
      if (users.length)
        return reject(
          state,
          `Vehicle ${users.map((v) => v.id).join(", ")} uses depot ${depots.join(", ")} on this node; reassign or delete it first.`,
        );
      return edit(state, {
        ...d,
        graph: {
          nodes: nodes.filter((n) => n.id !== action.id),
          edges: edges.filter((e) => e.source !== action.id && e.target !== action.id),
        },
        depots: d.depots.filter((x) => x.node_id !== action.id),
        customers: d.customers.filter((x) => x.node_id !== action.id),
      });
    }

    case "addEdge": {
      const { source, target } = action;
      const s = nodes.find((n) => n.id === source);
      const t = nodes.find((n) => n.id === target);
      if (!s || !t) return reject(state, "Both ends of a road must be existing nodes.");
      if (source === target) return reject(state, "A road cannot start and end at the same node.");
      const distance = Math.max(
        0.001,
        round(Math.hypot((t.x ?? 0) - (s.x ?? 0), (t.y ?? 0) - (s.y ?? 0))),
      );
      const time = round((distance / NEW_ROAD_KMH) * 60);
      const base = `${source}->${target}`;
      const ids = new Set(edges.map((e) => e.id));
      let id = base;
      for (let k = 2; ids.has(id); k++) id = `${base}#${k}`;
      return edit(state, {
        ...d,
        graph: {
          ...d.graph,
          edges: [
            ...edges,
            {
              id,
              source,
              target,
              distance,
              base_time: time,
              current_time: time,
              closed: false,
              road_class: "local",
              capacity: null,
              congestion: 1,
            },
          ],
        },
      });
    }

    case "updateEdge": {
      const e = edges.find((x) => x.id === action.id);
      if (!e) return reject(state, `Unknown road ${action.id}.`);
      for (const k of ["distance", "base_time", "current_time"] as const) {
        if (k in action.patch && !finiteNonNegative(action.patch[k]))
          return reject(state, `${k} must be a finite number ≥ 0.`);
      }
      const next = { ...e, ...action.patch };
      next.congestion = next.base_time > 0 ? round(next.current_time / next.base_time, 2) : null;
      return edit(state, {
        ...d,
        graph: { ...d.graph, edges: edges.map((x) => (x.id === e.id ? next : x)) },
      });
    }

    case "deleteEdge":
      if (!edges.some((e) => e.id === action.id))
        return reject(state, `Unknown road ${action.id}.`);
      return edit(state, {
        ...d,
        graph: { ...d.graph, edges: edges.filter((e) => e.id !== action.id) },
      });

    case "setRole": {
      if (!nodes.some((n) => n.id === action.nodeId))
        return reject(state, `Unknown node ${action.nodeId}.`);
      const depot = d.depots.find((x) => x.node_id === action.nodeId);
      const customer = d.customers.find((x) => x.node_id === action.nodeId);
      if (depot && action.role !== "depot") {
        const users = d.vehicles.filter(
          (v) => v.start_depot_id === depot.id || v.end_depot_ids.includes(depot.id),
        );
        if (users.length)
          return reject(
            state,
            `Vehicle ${users.map((v) => v.id).join(", ")} uses depot ${depot.id}; reassign or delete it first.`,
          );
      }
      let depots = d.depots.filter((x) => x.node_id !== action.nodeId || action.role === "depot");
      let customers = d.customers.filter(
        (x) => x.node_id !== action.nodeId || action.role === "customer",
      );
      if (action.role === "depot" && !depot)
        depots = [
          ...depots,
          {
            id: nextId(
              "d",
              d.depots.map((x) => x.id),
            ),
            node_id: action.nodeId,
          },
        ];
      if (action.role === "customer" && !customer)
        customers = [
          ...customers,
          {
            id: nextId(
              "c",
              d.customers.map((x) => x.id),
            ),
            node_id: action.nodeId,
            demand: 1,
          },
        ];
      return edit(state, { ...d, depots, customers });
    }

    case "setDemand": {
      if (!Number.isInteger(action.demand) || action.demand < 1)
        return reject(state, "Demand must be a whole number ≥ 1.");
      if (!d.customers.some((c) => c.id === action.customerId))
        return reject(state, `Unknown customer ${action.customerId}.`);
      return edit(state, {
        ...d,
        customers: d.customers.map((c) =>
          c.id === action.customerId ? { ...c, demand: action.demand } : c,
        ),
      });
    }

    case "addVehicle": {
      if (!d.depots.length) return reject(state, "Add a depot before adding vehicles.");
      const id = nextId(
        "v",
        d.vehicles.map((v) => v.id),
      );
      const capacity = d.vehicles.at(-1)?.capacity ?? 10;
      return edit(state, {
        ...d,
        vehicles: [
          ...d.vehicles,
          { id, capacity, start_depot_id: d.depots[0].id, end_depot_ids: [] },
        ],
      });
    }

    case "updateVehicle": {
      const v = d.vehicles.find((x) => x.id === action.id);
      if (!v) return reject(state, `Unknown vehicle ${action.id}.`);
      if (
        action.capacity !== undefined &&
        (!Number.isInteger(action.capacity) || action.capacity < 1)
      )
        return reject(state, "Capacity must be a whole number ≥ 1.");
      if (action.startDepotId !== undefined && !d.depots.some((x) => x.id === action.startDepotId))
        return reject(state, `Unknown depot ${action.startDepotId}.`);
      return edit(state, {
        ...d,
        vehicles: d.vehicles.map((x) =>
          x.id === v.id
            ? {
                ...x,
                capacity: action.capacity ?? x.capacity,
                start_depot_id: action.startDepotId ?? x.start_depot_id,
              }
            : x,
        ),
      });
    }

    case "deleteVehicle":
      if (!d.vehicles.some((v) => v.id === action.id))
        return reject(state, `Unknown vehicle ${action.id}.`);
      return edit(state, { ...d, vehicles: d.vehicles.filter((v) => v.id !== action.id) });
  }
}

/** Data as stored by the server (strip the version's id/name). */
export function toScenarioData(s: { id?: string; name?: string } & ScenarioData): ScenarioData {
  const { id: _id, name: _name, ...rest } = s;
  return rest;
}
