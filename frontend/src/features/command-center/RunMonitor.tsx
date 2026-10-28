"use client";

import { EmptyState, ErrorState, RunStatusBadge, Section, Stat } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useRunEvents } from "@/lib/api/events";
import { isTerminal, useCancelRun, useRun, useRuns } from "@/lib/api/hooks";
import type { RunEvent, RunOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/stores/workspace";
import { ALGORITHM_LABELS } from "./RunLauncher";

function describe(e: RunEvent): string {
  const p = e.payload as Record<string, unknown>;
  switch (e.type) {
    case "progress":
      return `iteration ${p.iteration} · best ${p.best_objective == null ? "–" : Number(p.best_objective).toFixed(3)} min`;
    case "started":
      return `started on ${String(p.worker_id ?? "worker")} (attempt ${p.attempt ?? 1})`;
    case "completed":
    case "cancelled":
      return `${e.type} · ${p.feasible ? `objective ${Number(p.objective).toFixed(3)} min` : "no feasible solution"}`;
    case "failed":
      return `failed · ${(p.error as { code?: string } | undefined)?.code ?? "error"}`;
    default:
      return e.type.replace("_", " ");
  }
}

function ActiveRun({ run }: { run: RunOut }) {
  const log = useRunEvents(run.id);
  const cancel = useCancelRun();
  const progress = log.latestProgress ?? run.progress;
  const terminal = isTerminal(run);
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="grid content-start gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <RunStatusBadge status={run.status} />
          <span className="text-xs">{ALGORITHM_LABELS[run.algorithm_id] ?? run.algorithm_id}</span>
          <span className="num text-text-muted text-xs">
            seed {run.seed ?? "n/a"} · attempt {run.attempt}/{run.max_attempts}
          </span>
          <span className="num text-text-muted text-xs" title={run.id}>
            {run.id.slice(0, 8)}
          </span>
          <Button
            size="xs"
            variant="destructive"
            className="ml-auto"
            disabled={terminal || run.status === "CANCELLING" || cancel.isPending}
            onClick={() => cancel.mutate(run.id)}
          >
            {run.status === "CANCELLING" ? "Cancelling…" : "Cancel run"}
          </Button>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
          <Stat label="Iteration" value={progress?.iteration ?? null} digits={0} />
          <Stat label="Evaluations" value={progress?.evaluations ?? null} digits={0} />
          <Stat
            label="Best objective"
            value={progress?.best_objective ?? null}
            unit="min"
            digits={3}
          />
          <Stat label="Elapsed" value={progress?.elapsed_s ?? null} unit="s" kind="measured" />
        </dl>
        {progress && !progress.has_feasible && (
          <p className="text-traffic-congested text-xs">No feasible solution found yet.</p>
        )}
        {run.error && (
          <ErrorState
            error={new Error(run.error.message ?? run.error.code)}
            title={`Run failed (${run.error.code})`}
          />
        )}
        {cancel.isError && <ErrorState error={cancel.error} title="Cancel failed" />}
        <p className="text-text-muted text-[11px]">
          Latest progress report from the worker (reports are throttled
          {terminal ? "; final counts are under Best solution" : ""}). Live updates:{" "}
          {log.connection === "open" ? "connected" : log.connection}
          {log.ended && " · stream finished"}. There is no percentage because the remaining work is
          not known in advance.
        </p>
      </div>
      <div>
        <h3 className="text-muted-foreground mb-1 text-xs">Event log</h3>
        {log.events.length === 0 ? (
          <EmptyState>Waiting for events…</EmptyState>
        ) : (
          <ol className="num grid max-h-36 gap-0.5 overflow-y-auto text-[11px]" aria-live="polite">
            {log.events
              .filter(
                (e, i, all) =>
                  e.kind === "lifecycle" ||
                  i === all.length - 1 ||
                  all[i + 1]?.kind === "lifecycle",
              )
              .map((e) => (
                <li
                  key={e.id}
                  className={cn(
                    e.kind === "lifecycle" ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  <span className="text-text-muted">
                    {new Date(e.created_at).toLocaleTimeString()}
                  </span>{" "}
                  {describe(e)}
                </li>
              ))}
          </ol>
        )}
      </div>
    </div>
  );
}

export function RunMonitor() {
  const versionId = useWorkspace((s) => s.versionId);
  const activeRunId = useWorkspace((s) => s.activeRunId);
  const setActiveRun = useWorkspace((s) => s.setActiveRun);
  const run = useRun(activeRunId);
  const runs = useRuns(versionId);

  return (
    <div className="grid h-full gap-0 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <Section title="Active run" className="border-b-0">
        {!activeRunId && (
          <EmptyState>No run selected. Launch one from the controls panel.</EmptyState>
        )}
        {run.isError && <ErrorState error={run.error} />}
        {run.data && <ActiveRun run={run.data} />}
      </Section>
      <Section title="Runs on this version" className="border-l-0 lg:border-l">
        {!versionId && <EmptyState>Load a scenario to see its runs.</EmptyState>}
        {runs.data?.items.length === 0 && <EmptyState>No runs yet.</EmptyState>}
        <ul className="grid gap-0.5">
          {runs.data?.items.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => setActiveRun(r.id)}
                aria-pressed={r.id === activeRunId}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1 text-left text-xs",
                  r.id === activeRunId ? "bg-secondary" : "hover:bg-secondary/60",
                )}
              >
                <span className="truncate">
                  {ALGORITHM_LABELS[r.algorithm_id] ?? r.algorithm_id}
                </span>
                <RunStatusBadge status={r.status} />
              </button>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
