"use client";

import { useQueries } from "@tanstack/react-query";
import { useState } from "react";

import { ConvergenceChart } from "@/components/charts/ConvergenceChart";
import { historyToPoints, type XAxis } from "@/components/charts/convergence";
import { EmptyState, ErrorState, LoadingState, RunStatusBadge, Section } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ALGORITHM_LABELS } from "@/features/command-center/RunLauncher";
import { api } from "@/lib/api/client";
import { keys, useRunList, useSavedScenarios } from "@/lib/api/hooks";
import type { RunFilters, RunOut, RunResultOut, RunStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUSES: RunStatus[] = [
  "QUEUED",
  "RUNNING",
  "CANCELLING",
  "CANCELLED",
  "COMPLETED",
  "FAILED",
];
const MAX_COMPARE = 6;
const PAGE = 25;

const fmt = (v: number | null | undefined, d = 3) => (v == null ? "–" : v.toFixed(d));

/** Rows of the side-by-side comparison; `kind` marks measured vs derived quantities. */
export const COMPARE_ROWS: {
  label: string;
  kind?: "measured" | "derived";
  value: (run: RunOut, r: RunResultOut | undefined) => string;
}[] = [
  { label: "Algorithm", value: (run) => `${run.algorithm_id} v${run.algorithm_version}` },
  { label: "Status", value: (run) => run.status },
  { label: "Seed", value: (run) => (run.seed == null ? "n/a" : String(run.seed)) },
  { label: "Objective (min)", kind: "derived", value: (_, r) => fmt(r?.objective) },
  { label: "Feasible", value: (_, r) => (r ? (r.feasible ? "yes" : "no") : "–") },
  { label: "Distance (km)", kind: "derived", value: (_, r) => fmt(r?.total_distance) },
  { label: "Iterations", value: (_, r) => (r ? String(r.iterations) : "–") },
  {
    label: "Evaluations",
    value: (_, r) => (r?.evaluations == null ? "n/a" : String(r.evaluations)),
  },
  { label: "Wall time (s)", kind: "measured", value: (_, r) => fmt(r?.elapsed_s, 2) },
  {
    label: "First feasible (s)",
    kind: "measured",
    value: (_, r) => fmt(r?.time_to_first_feasible_s, 3),
  },
  { label: "Stopped", value: (_, r) => r?.termination_reason ?? "–" },
  {
    label: "Optimality",
    value: (_, r) =>
      r ? (r.optimality === "proven_optimal" ? "proven optimum" : "not proven") : "–",
  },
  { label: "Scenario version", value: (run) => run.scenario_version_id.slice(0, 8) },
];

function RunDetail({ run, result }: { run: RunOut; result: RunResultOut | undefined }) {
  const software = (result?.diagnostics.software ?? {}) as Record<string, string>;
  return (
    <Section title={`Run ${run.id.slice(0, 8)}: reproducibility`}>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
        <dt className="text-muted-foreground">run id</dt>
        <dd className="num break-all">{run.id}</dd>
        <dt className="text-muted-foreground">scenario version</dt>
        <dd className="num break-all">{run.scenario_version_id}</dd>
        <dt className="text-muted-foreground">algorithm</dt>
        <dd className="num">
          {run.algorithm_id} v{run.algorithm_version}
        </dd>
        <dt className="text-muted-foreground">seed</dt>
        <dd className="num">{run.seed ?? "n/a (seedless solver)"}</dd>
        <dt className="text-muted-foreground">attempt</dt>
        <dd className="num">
          {run.attempt}/{run.max_attempts}
        </dd>
        {Object.entries(run.config).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="num text-muted-foreground">config.{k}</dt>
            <dd className="num truncate">{JSON.stringify(v)}</dd>
          </div>
        ))}
        {result && (
          <>
            <dt className="text-muted-foreground">evaluator</dt>
            <dd className="num">v{result.evaluation?.evaluator_version ?? "?"}</dd>
          </>
        )}
        {Object.entries(software).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="num text-muted-foreground">{k}</dt>
            <dd className="num truncate">{v}</dd>
          </div>
        ))}
      </dl>
      {run.error && (
        <p className="text-incident-text mt-2 text-xs">
          Error: {run.error.code} {run.error.message ?? ""}
        </p>
      )}
    </Section>
  );
}

export function RunsTab() {
  const scenarios = useSavedScenarios();
  const [filters, setFilters] = useState<RunFilters>({ limit: PAGE, offset: 0 });
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<string | null>(null);
  const [axis, setAxis] = useState<XAxis>("elapsed_s");
  const list = useRunList(filters);
  const set = (patch: Partial<RunFilters>) =>
    setFilters((f) => ({ ...f, ...patch, offset: patch.offset ?? 0 }));

  const runsById = new Map((list.data?.items ?? []).map((r) => [r.id, r]));
  const runQueries = useQueries({
    queries: selected.map((id) => ({ queryKey: keys.run(id), queryFn: () => api.getRun(id) })),
  });
  const resultQueries = useQueries({
    queries: selected.map((id, i) => {
      const run = runQueries[i]?.data ?? runsById.get(id);
      const ready =
        run && (run.status === "COMPLETED" || (run.status === "CANCELLED" && !!run.started_at));
      return {
        queryKey: keys.result(id),
        queryFn: () => api.getRunResult(id),
        enabled: !!ready,
        staleTime: Infinity,
        retry: false,
      };
    }),
  });
  const compared = selected
    .map((id, i) => ({
      run: runQueries[i]?.data ?? runsById.get(id),
      result: resultQueries[i]?.data,
    }))
    .filter((x): x is { run: RunOut; result: RunResultOut | undefined } => !!x.run);
  const series = compared
    .filter((c) => c.result)
    .map((c) => ({
      name: `${c.run.algorithm_id} · seed ${c.run.seed ?? "n/a"} · ${c.run.id.slice(0, 6)}`,
      source: "stored" as const,
      points: historyToPoints(c.result!.history, axis),
    }));
  const algorithmsDiffer = new Set(compared.map((c) => c.run.algorithm_id)).size > 1;
  const versionsDiffer = new Set(compared.map((c) => c.run.scenario_version_id)).size > 1;
  const detailRun =
    compared.find((c) => c.run.id === detail) ??
    (detail ? { run: runsById.get(detail)!, result: undefined } : null);

  return (
    <div className="grid gap-4">
      <Section title="Filters">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <div className="grid gap-1">
            <Label htmlFor="f-scenario" className="text-xs">
              Scenario
            </Label>
            <NativeSelect
              id="f-scenario"
              value={filters.scenario_id ?? ""}
              onChange={(e) => set({ scenario_id: e.target.value || undefined })}
            >
              <option value="">All</option>
              {scenarios.data?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="f-algorithm" className="text-xs">
              Algorithm
            </Label>
            <NativeSelect
              id="f-algorithm"
              value={filters.algorithm_id ?? ""}
              onChange={(e) => set({ algorithm_id: e.target.value || undefined })}
            >
              <option value="">All</option>
              {Object.entries(ALGORITHM_LABELS).map(([id, l]) => (
                <option key={id} value={id}>
                  {l}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="f-status" className="text-xs">
              Status
            </Label>
            <NativeSelect
              id="f-status"
              value={filters.status ?? ""}
              onChange={(e) =>
                set({ status: (e.target.value || undefined) as RunStatus | undefined })
              }
            >
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="f-from" className="text-xs">
              From (date)
            </Label>
            <Input
              id="f-from"
              type="date"
              className="h-8"
              onChange={(e) =>
                set({
                  created_after: e.target.value
                    ? new Date(e.target.value).toISOString()
                    : undefined,
                })
              }
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="f-to" className="text-xs">
              Until (date, exclusive)
            </Label>
            <Input
              id="f-to"
              type="date"
              className="h-8"
              onChange={(e) =>
                set({
                  created_before: e.target.value
                    ? new Date(e.target.value).toISOString()
                    : undefined,
                })
              }
            />
          </div>
        </div>
      </Section>

      <Section
        title={`Run history${list.data ? ` (${list.data.total})` : ""}`}
        actions={
          <span className="text-muted-foreground text-xs">
            Select up to {MAX_COMPARE} runs to compare
          </span>
        }
      >
        {list.isPending && <LoadingState label="Loading runs…" />}
        {list.isError && <ErrorState error={list.error} />}
        {list.data && list.data.items.length === 0 && (
          <EmptyState>No runs match these filters.</EmptyState>
        )}
        {list.data && list.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">Runs</caption>
              <thead className="text-muted-foreground">
                <tr>
                  <th scope="col" className="py-1 pr-2">
                    Compare
                  </th>
                  <th scope="col" className="pr-2">
                    Created
                  </th>
                  <th scope="col" className="pr-2">
                    Algorithm
                  </th>
                  <th scope="col" className="pr-2">
                    Seed
                  </th>
                  <th scope="col" className="pr-2">
                    Status
                  </th>
                  <th scope="col" className="pr-2">
                    Suite
                  </th>
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((r) => {
                  const checked = selected.includes(r.id);
                  return (
                    <tr key={r.id} className={cn("border-t", checked && "bg-secondary/60")}>
                      <td className="py-1 pr-2">
                        <input
                          type="checkbox"
                          className="accent-[var(--tq-signal)]"
                          aria-label={`Compare run ${r.id.slice(0, 8)}`}
                          checked={checked}
                          disabled={!checked && selected.length >= MAX_COMPARE}
                          onChange={(e) =>
                            setSelected((s) =>
                              e.target.checked ? [...s, r.id] : s.filter((x) => x !== r.id),
                            )
                          }
                        />
                      </td>
                      <td className="num pr-2">{new Date(r.created_at).toLocaleString()}</td>
                      <td className="pr-2">{ALGORITHM_LABELS[r.algorithm_id] ?? r.algorithm_id}</td>
                      <td className="num pr-2">{r.seed ?? "n/a"}</td>
                      <td className="pr-2">
                        <RunStatusBadge status={r.status} />
                      </td>
                      <td className="num pr-2">
                        {r.suite_spec ? `${r.suite_spec} #${r.repetition}` : "–"}
                      </td>
                      <td>
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={() => setDetail(r.id)}
                          aria-label={`Details of run ${r.id.slice(0, 8)}`}
                        >
                          {r.id.slice(0, 8)}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.total > PAGE && (
          <div className="mt-2 flex items-center gap-2 text-xs">
            <Button
              size="xs"
              variant="outline"
              disabled={(filters.offset ?? 0) === 0}
              onClick={() =>
                setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - PAGE) }))
              }
            >
              Previous
            </Button>
            <span className="num">
              {(filters.offset ?? 0) + 1}–{Math.min((filters.offset ?? 0) + PAGE, list.data.total)}{" "}
              of {list.data.total}
            </span>
            <Button
              size="xs"
              variant="outline"
              disabled={(filters.offset ?? 0) + PAGE >= list.data.total}
              onClick={() => setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + PAGE }))}
            >
              Next
            </Button>
          </div>
        )}
      </Section>

      {compared.length > 0 && (
        <Section title={`Comparison (${compared.length} runs, stored results)`}>
          {(algorithmsDiffer || versionsDiffer) && (
            <p className="text-traffic-congested mb-2 text-xs">
              {versionsDiffer &&
                "Runs use different scenario versions: objectives are not directly comparable. "}
              {algorithmsDiffer &&
                "Algorithms use different budget units (time, moves, particle updates); compare wall time alongside objective."}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs" aria-label="Run comparison">
              <thead>
                <tr>
                  <th scope="col" className="text-muted-foreground py-1 pr-3">
                    Quantity
                  </th>
                  {compared.map((c) => (
                    <th key={c.run.id} scope="col" className="num pr-3">
                      {c.run.id.slice(0, 8)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE_ROWS.map((row) => (
                  <tr key={row.label} className="border-t">
                    <th scope="row" className="text-muted-foreground py-1 pr-3 font-normal">
                      {row.label}
                      {row.kind && (
                        <span className="text-muted-foreground ml-1 text-[10px]">{row.kind}</span>
                      )}
                    </th>
                    {compared.map((c) => (
                      <td key={c.run.id} className="num pr-3">
                        {row.value(c.run, c.result)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <h3 className="text-xs font-semibold">Convergence (stored history)</h3>
            <NativeSelect
              aria-label="x-axis"
              className="w-auto"
              value={axis}
              onChange={(e) => setAxis(e.target.value as XAxis)}
            >
              <option value="elapsed_s">elapsed wall time</option>
              <option value="iteration">iteration</option>
            </NativeSelect>
          </div>
          <ConvergenceChart
            series={series}
            axis={axis}
            height={280}
            label="Best feasible objective of the compared runs"
          />
        </Section>
      )}

      {detailRun?.run && <RunDetail run={detailRun.run} result={detailRun.result} />}
    </div>
  );
}
