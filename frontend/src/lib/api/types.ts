// Mirrors backend/src/trafiqon/api/schemas.py. Keep in sync.

export type Algorithm = "dijkstra" | "astar";

export interface NodeOut {
  id: string;
  x: number | null;
  y: number | null;
  label: string | null;
}

export interface EdgeOut {
  id: string;
  source: string;
  target: string;
  distance: number;
  base_time: number;
  current_time: number;
  closed: boolean;
  road_class: string | null;
  capacity: number | null;
  congestion: number | null;
}

export interface ScenarioOut {
  id: string;
  name: string;
  description: string;
  synthetic: boolean;
  settings: Record<string, unknown>;
  graph: { nodes: NodeOut[]; edges: EdgeOut[] };
  depots: { id: string; node_id: string }[];
  customers: { id: string; node_id: string; demand: number }[];
  vehicles: { id: string; capacity: number; start_depot_id: string; end_depot_ids: string[] }[];
}

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  synthetic: boolean;
  node_count: number;
  edge_count: number;
  customer_count: number;
  vehicle_count: number;
}

export interface PathOut {
  node_ids: string[];
  edge_ids: string[];
  travel_time: number;
  distance: number;
}

export interface ShortestPathRequest {
  scenario_id: string;
  source: string;
  target: string;
  algorithm: Algorithm;
}

export interface ShortestPathResponse {
  scenario_id: string;
  algorithm: Algorithm;
  source: string;
  target: string;
  reachable: boolean;
  path: PathOut | null;
  expanded_nodes: number;
  evaluator_version: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
