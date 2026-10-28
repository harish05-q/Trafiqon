import type {
  ApiErrorBody,
  ScenarioOut,
  ScenarioSummary,
  ShortestPathRequest,
  ShortestPathResponse,
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
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
    );
  }
  return (await res.json()) as T;
}

export const api = {
  listBuiltinScenarios: () => request<ScenarioSummary[]>("/api/v1/scenarios/builtin"),
  getBuiltinScenario: (id: string) =>
    request<ScenarioOut>(`/api/v1/scenarios/builtin/${encodeURIComponent(id)}`),
  shortestPath: (body: ShortestPathRequest) =>
    request<ShortestPathResponse>("/api/v1/routing/shortest-path", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
