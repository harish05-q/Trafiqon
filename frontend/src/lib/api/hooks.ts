"use client";

// TanStack Query hooks: the only way components read or change server state.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { TERMINAL_STATUSES, type RunCreate, type RunOut } from "./types";

export const keys = {
  health: ["health"] as const,
  algorithms: ["algorithms"] as const,
  builtin: ["scenarios", "builtin"] as const,
  scenarios: ["scenarios", "saved"] as const,
  scenario: (id: string) => ["scenarios", "saved", id] as const,
  version: (id: string) => ["versions", id] as const,
  runs: (versionId?: string) => ["runs", { versionId }] as const,
  run: (id: string) => ["runs", id] as const,
  result: (id: string) => ["runs", id, "result"] as const,
};

export function isTerminal(run: Pick<RunOut, "status"> | undefined): boolean {
  return !!run && TERMINAL_STATUSES.includes(run.status);
}

export function useHealth() {
  // Real liveness check every 15 s; the top bar shows what it returns.
  return useQuery({
    queryKey: keys.health,
    queryFn: api.health,
    refetchInterval: 15_000,
    retry: 0,
  });
}

export function useAlgorithms() {
  return useQuery({ queryKey: keys.algorithms, queryFn: api.algorithms, staleTime: Infinity });
}

export function useBuiltinScenarios() {
  return useQuery({
    queryKey: keys.builtin,
    queryFn: api.listBuiltinScenarios,
    staleTime: Infinity,
  });
}

export function useSavedScenarios() {
  return useQuery({ queryKey: keys.scenarios, queryFn: () => api.listScenarios() });
}

export function useVersion(versionId: string | null) {
  return useQuery({
    queryKey: keys.version(versionId ?? ""),
    queryFn: () => api.getVersion(versionId!),
    enabled: !!versionId,
    staleTime: Infinity, // versions are immutable
  });
}

export function useImportBuiltin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, builtinId }: { name: string; builtinId: string }) =>
      api.createScenarioFromBuiltin(name, builtinId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.scenarios }),
  });
}

export function useRuns(versionId: string | null) {
  return useQuery({
    queryKey: keys.runs(versionId ?? undefined),
    queryFn: () => api.listRuns({ scenario_version_id: versionId ?? undefined, limit: 20 }),
    enabled: !!versionId,
  });
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: keys.run(runId ?? ""),
    queryFn: () => api.getRun(runId!),
    enabled: !!runId,
    // Polling is a fallback; SSE events invalidate this query as they arrive.
    refetchInterval: (q) => (isTerminal(q.state.data) ? false : 5_000),
  });
}

export function useRunResult(run: RunOut | undefined) {
  const ready =
    !!run && (run.status === "COMPLETED" || (run.status === "CANCELLED" && !!run.started_at));
  return useQuery({
    queryKey: keys.result(run?.id ?? ""),
    queryFn: () => api.getRunResult(run!.id),
    enabled: ready,
    staleTime: Infinity, // results are stored once
    retry: false,
  });
}

export function useSubmitRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RunCreate) => api.submitRun(body),
    onSuccess: (run) => {
      qc.setQueryData(keys.run(run.id), run);
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useCancelRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.cancelRun(runId),
    // Not optimistic: the server decides between CANCELLED and CANCELLING.
    onSettled: (_d, _e, runId) => qc.invalidateQueries({ queryKey: keys.run(runId) }),
  });
}
