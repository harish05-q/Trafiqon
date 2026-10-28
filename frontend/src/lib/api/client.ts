import type {
  AlgorithmInfo,
  ApiErrorBody,
  HealthOut,
  Page,
  RunCreate,
  RunOut,
  RunResultOut,
  RunStatus,
  ScenarioDetail,
  ScenarioOut,
  ScenarioRecord,
  ScenarioSummary,
  ShortestPathRequest,
  ShortestPathResponse,
  VersionOut,
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the API at ${API_BASE_URL}`);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      res.status,
      body?.error.code ?? `http_${res.status}`,
      body?.error.message ?? res.statusText,
      body?.error.details,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params))
    if (v !== undefined && v !== null) q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<HealthOut>("/api/v1/health"),
  algorithms: () => request<AlgorithmInfo[]>("/api/v1/algorithms"),

  listBuiltinScenarios: () => request<ScenarioSummary[]>("/api/v1/scenarios/builtin"),
  getBuiltinScenario: (id: string) =>
    request<ScenarioOut>(`/api/v1/scenarios/builtin/${encodeURIComponent(id)}`),
  shortestPath: (body: ShortestPathRequest) =>
    request<ShortestPathResponse>("/api/v1/routing/shortest-path", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listScenarios: (limit = 50, offset = 0) =>
    request<Page<ScenarioRecord>>(`/api/v1/scenarios${query({ limit, offset })}`),
  getScenario: (id: string) => request<ScenarioDetail>(`/api/v1/scenarios/${id}`),
  createScenarioFromBuiltin: (name: string, builtinId: string) =>
    request<ScenarioDetail>("/api/v1/scenarios", {
      method: "POST",
      body: JSON.stringify({ name, builtin_id: builtinId }),
    }),
  getVersion: (versionId: string) => request<VersionOut>(`/api/v1/scenario-versions/${versionId}`),

  listRuns: (p: { scenario_version_id?: string; status?: RunStatus; limit?: number } = {}) =>
    request<Page<RunOut>>(`/api/v1/runs${query({ limit: 20, ...p })}`),
  getRun: (id: string) => request<RunOut>(`/api/v1/runs/${id}`),
  submitRun: (body: RunCreate) =>
    request<RunOut>("/api/v1/runs", { method: "POST", body: JSON.stringify(body) }),
  cancelRun: (id: string) =>
    request<{ id: string; status: RunStatus }>(`/api/v1/runs/${id}/cancel`, { method: "POST" }),
  getRunResult: (id: string) => request<RunResultOut>(`/api/v1/runs/${id}/result`),
  runEventsUrl: (id: string) => `${API_BASE_URL}/api/v1/runs/${id}/events`,
};
