// A tiny in-memory fake of the TRAFIQON API for component tests. It mirrors the backend's
// response shapes; tests assert on what the UI does with real-shaped responses.
import { vi } from "vitest";

import type {
  AlgorithmInfo,
  RunOut,
  RunResultOut,
  ScenarioOut,
  ScenarioRecord,
  VersionOut,
} from "@/lib/api/types";

export const scenarioData: ScenarioOut = {
  id: "s1",
  name: "Urban Grid",
  description: "",
  synthetic: true,
  settings: {},
  graph: {
    nodes: [
      { id: "n0", x: 0, y: 0, label: null },
      { id: "n1", x: 1, y: 0, label: null },
    ],
    edges: [
      {
        id: "n0->n1",
        source: "n0",
        target: "n1",
        distance: 1,
        base_time: 2,
        current_time: 2,
        closed: false,
        road_class: "local",
        capacity: null,
        congestion: 1,
      },
      {
        id: "n1->n0",
        source: "n1",
        target: "n0",
        distance: 1,
        base_time: 2,
        current_time: 2,
        closed: false,
        road_class: "local",
        capacity: null,
        congestion: 1,
      },
    ],
  },
  depots: [{ id: "d1", node_id: "n0" }],
  customers: [{ id: "c1", node_id: "n1", demand: 3 }],
  vehicles: [{ id: "v1", capacity: 10, start_depot_id: "d1", end_depot_ids: [] }],
};

export const version: VersionOut = {
  id: "ver-1",
  scenario_id: "s1",
  version_number: 1,
  fingerprint: "abcdef0123456789",
  synthetic: true,
  node_count: 2,
  edge_count: 2,
  customer_count: 1,
  vehicle_count: 1,
  note: "",
  created_at: "2026-10-28T00:00:00Z",
  data: scenarioData,
};

export const savedScenario: ScenarioRecord = {
  id: "s1",
  name: "Urban Grid",
  description: "",
  current_version_id: "ver-1",
  created_at: "2026-10-28T00:00:00Z",
  updated_at: "2026-10-28T00:00:00Z",
};

export const algorithms: AlgorithmInfo[] = [
  { id: "ortools_cvrp", version: "1", uses_seed: false, defaults: { time_limit_s: 2 } },
  { id: "simulated_annealing", version: "1", uses_seed: true, defaults: { max_iterations: 20000 } },
  {
    id: "qpso_hybrid",
    version: "1",
    uses_seed: true,
    defaults: { iterations: 100, swarm_size: 20 },
  },
];

export function makeRun(over: Partial<RunOut> = {}): RunOut {
  return {
    id: "run-1",
    scenario_version_id: "ver-1",
    suite_id: null,
    suite_spec: null,
    repetition: null,
    algorithm_id: "qpso_hybrid",
    algorithm_version: "1",
    config: {},
    seed: 42,
    status: "QUEUED",
    attempt: 0,
    max_attempts: 2,
    created_at: "2026-10-28T00:00:00Z",
    started_at: null,
    cancel_requested_at: null,
    finished_at: null,
    progress: null,
    termination_reason: null,
    error: null,
    ...over,
  };
}

export const result: RunResultOut = {
  run_id: "run-1",
  feasible: true,
  objective: 4,
  total_distance: 2,
  solution: {
    routes: [{ vehicle_id: "v1", customer_ids: ["c1"], start_depot_id: "d1", end_depot_id: "d1" }],
  },
  evaluation: {
    feasible: true,
    objective: 4,
    total_distance: 2,
    evaluator_version: "1",
    violations: [],
    routes: [
      {
        vehicle_id: "v1",
        customer_ids: ["c1"],
        load: 3,
        capacity: 10,
        travel_time: 4,
        distance: 2,
        legs: [
          {
            source_node: "n0",
            target_node: "n1",
            node_ids: ["n0", "n1"],
            edge_ids: ["n0->n1"],
            travel_time: 2,
            distance: 1,
          },
          {
            source_node: "n1",
            target_node: "n0",
            node_ids: ["n1", "n0"],
            edge_ids: ["n1->n0"],
            travel_time: 2,
            distance: 1,
          },
        ],
      },
    ],
  },
  iterations: 10,
  evaluations: 500,
  elapsed_s: 0.5,
  time_to_first_feasible_s: 0.01,
  termination_reason: "iteration_limit",
  optimality: "not_proven",
  seed: 42,
  history: [],
  diagnostics: {},
  created_at: "2026-10-28T00:00:00Z",
};

type Handler = (url: URL, init?: RequestInit) => unknown | Promise<unknown>;

export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Install a fetch mock routed by "METHOD /path". Unmatched requests get a 404 error body. */
export function installFetch(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input);
    const method = init?.method ?? "GET";
    calls.push({
      method,
      path: url.pathname,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    const handler = routes[`${method} ${url.pathname}`];
    if (!handler)
      return json({ error: { code: "not_found", message: `${method} ${url.pathname}` } }, 404);
    const out = await handler(url, init);
    return out instanceof Response ? out : json(out);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

/** Minimal EventSource stand-in: tests push events with `emit`. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, ((e: MessageEvent<string>) => void)[]>();
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  emit(type: string, data: unknown) {
    for (const fn of this.listeners.get(type) ?? []) {
      fn(new MessageEvent(type, { data: JSON.stringify(data) }));
    }
  }
  close() {
    this.readyState = 2;
  }
}
