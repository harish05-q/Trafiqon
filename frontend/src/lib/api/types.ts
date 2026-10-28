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

// --- persisted resources (backend/src/trafiqon/api/schemas.py) ---------------------------

export type ScenarioData = Omit<ScenarioOut, "id" | "name">;

export interface VersionSummary {
  id: string;
  scenario_id: string;
  version_number: number;
  fingerprint: string;
  synthetic: boolean;
  node_count: number;
  edge_count: number;
  customer_count: number;
  vehicle_count: number;
  note: string;
  created_at: string;
}

export interface VersionOut extends VersionSummary {
  data: ScenarioOut;
}

export interface ScenarioRecord {
  id: string;
  name: string;
  description: string;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScenarioDetail extends ScenarioRecord {
  versions: VersionSummary[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type AlgorithmId = "ortools_cvrp" | "simulated_annealing" | "qpso_hybrid";

export interface AlgorithmInfo {
  id: AlgorithmId;
  version: string;
  uses_seed: boolean;
  defaults: Record<string, unknown>;
}

export type RunStatus = "QUEUED" | "RUNNING" | "CANCELLING" | "CANCELLED" | "COMPLETED" | "FAILED";
export const TERMINAL_STATUSES: readonly RunStatus[] = ["CANCELLED", "COMPLETED", "FAILED"];

export interface RunProgress {
  iteration: number;
  evaluations: number | null;
  elapsed_s: number;
  best_objective: number | null;
  current_objective: number | null;
  has_feasible: boolean;
  message: string;
  attempt: number;
}

export interface RunOut {
  id: string;
  scenario_version_id: string;
  suite_id: string | null;
  suite_spec: string | null;
  repetition: number | null;
  algorithm_id: AlgorithmId;
  algorithm_version: string;
  config: Record<string, unknown>;
  seed: number | null;
  status: RunStatus;
  attempt: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  cancel_requested_at: string | null;
  finished_at: string | null;
  progress: RunProgress | null;
  termination_reason: string | null;
  error: { code: string; message?: string; type?: string } | null;
}

export interface RunCreate {
  scenario_version_id: string;
  algorithm_id: AlgorithmId;
  config?: Record<string, unknown>;
  seed?: number | null;
  idempotency_key?: string;
}

export interface LegResult {
  source_node: string;
  target_node: string;
  node_ids: string[];
  edge_ids: string[];
  travel_time: number | null;
  distance: number | null;
}

export interface RouteResult {
  vehicle_id: string;
  customer_ids: string[];
  load: number;
  capacity: number | null;
  travel_time: number | null;
  distance: number | null;
  legs: LegResult[];
}

export interface HistoryPoint {
  iteration: number;
  evaluations: number | null;
  elapsed_s: number;
  current_objective: number | null;
  best_objective: number | null;
}

export interface RunResultOut {
  run_id: string;
  feasible: boolean;
  objective: number | null;
  total_distance: number | null;
  solution: {
    routes: {
      vehicle_id: string;
      customer_ids: string[];
      start_depot_id: string;
      end_depot_id: string;
    }[];
  } | null;
  evaluation: {
    feasible: boolean;
    objective: number | null;
    total_distance: number | null;
    evaluator_version: string;
    violations: { code: string; message: string }[];
    routes: RouteResult[];
  } | null;
  iterations: number;
  evaluations: number | null;
  elapsed_s: number;
  time_to_first_feasible_s: number | null;
  termination_reason: string;
  optimality: "proven_optimal" | "not_proven";
  seed: number | null;
  history: HistoryPoint[];
  diagnostics: Record<string, unknown>;
  created_at: string;
}

export interface RunEvent {
  id: number;
  kind: "lifecycle" | "progress";
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface HealthOut {
  status: "ok";
  version: string;
  api_version: "v1";
  dependencies: Record<string, { status: "ok" | "unavailable" | "not_configured" }>;
}

// --- M6 additions ----------------------------------------------------------------------------

export interface ParamOut {
  key: string;
  kind: "int" | "float" | "bool" | "enum" | "enum_list";
  description: string;
  minimum: number | null;
  maximum: number | null;
  nullable: boolean;
  null_meaning: string;
  choices: string[];
  unit: string;
  advanced: boolean;
  default: unknown;
}

export interface AlgorithmInfoFull extends AlgorithmInfo {
  params: ParamOut[];
}

export interface ValidationIssue {
  code: string;
  message: string;
  severity: "error" | "infeasible" | "warning";
  ref: string | null;
}

export interface ScenarioValidation {
  valid: boolean;
  feasible_so_far: boolean;
  issues: ValidationIssue[];
  strongly_connected_components: number | null;
  unreachable_location_pairs: number | null;
  total_demand: number | null;
  total_capacity: number | null;
}

export interface RunFilters {
  scenario_id?: string;
  scenario_version_id?: string;
  algorithm_id?: string;
  status?: RunStatus;
  suite_id?: string;
  created_after?: string;
  created_before?: string;
  limit?: number;
  offset?: number;
}

export interface SuiteSpec {
  algorithm_id: AlgorithmId;
  config: Record<string, unknown>;
  label?: string;
}

export interface SuiteOut {
  id: string;
  name: string;
  scenario_version_id: string;
  specs: {
    label: string;
    algorithm_id: AlgorithmId;
    algorithm_version: string;
    config: Record<string, unknown>;
  }[];
  seeds: number[];
  repetitions: number;
  budget_policy: string;
  created_at: string;
  status_counts: Partial<Record<RunStatus, number>>;
  run_ids: string[];
}

export interface SuiteSummary {
  spec: string;
  algorithm_id: string;
  n: number;
  feasible_count: number;
  feasible_rate: number;
  objective_mean: number | null;
  objective_median: number | null;
  objective_std: number | null;
  objective_best: number | null;
  objective_worst: number | null;
  elapsed_mean_s: number;
  elapsed_median_s: number;
  gap_mean_percent: number | null;
}

export interface SuiteComparison {
  metadata: Record<string, unknown>;
  reference: {
    kind: "proven_optimum" | "best_observed_heuristic";
    objective: number;
    source_spec: string;
    source_seed: number | null;
    source_repetition: number;
  } | null;
  quantity_kinds: Record<string, "measured" | "derived">;
  summaries: SuiteSummary[];
  status_counts_by_spec: Record<string, Partial<Record<RunStatus, number>>>;
  complete: boolean;
}
