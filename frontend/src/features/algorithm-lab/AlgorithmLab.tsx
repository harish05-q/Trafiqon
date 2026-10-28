"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ConvergenceChart } from "@/components/charts/ConvergenceChart";
import {
  historyToPoints,
  type ConvergenceSeries,
  type XAxis,
} from "@/components/charts/convergence";
import {
  ParamForm,
  changedOnly,
  defaultValues,
  formErrors,
  type ParamValues,
} from "@/components/params/ParamForm";
import { WorkspaceLayout } from "@/components/shell/WorkspaceLayout";
import { EmptyState, ErrorState, LoadingState, Section, Stat } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ALGORITHM_LABELS } from "@/features/command-center/RunLauncher";
import { RunMonitor } from "@/features/command-center/RunMonitor";
import { ApiError } from "@/lib/api/client";
import { useRunEventLog } from "@/lib/api/events";
import {
  useAlgorithms,
  useRun,
  useRunResult,
  useSubmitRun,
  useValidation,
  useVersion,
} from "@/lib/api/hooks";
import type { AlgorithmId, RunEvent, RunOut, RunResultOut, ScenarioOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/stores/workspace";

export function liveSeries(events: RunEvent[], axis: XAxis): ConvergenceSeries {
  const history = events
    .filter((e) => e.kind === "progress")
    .map(
      (e) => e.payload as { iteration: number; elapsed_s: number; best_objective: number | null },
    );
  return { name: "Live progress reports", source: "live", points: historyToPoints(history, axis) };
}

function ConfigPanel() {
  const algorithms = useAlgorithms();
  const versionId = useWorkspace((s) => s.versionId);
  const setActiveRun = useWorkspace((s) => s.setActiveRun);
  const submit = useSubmitRun();
  const [algorithmId, setAlgorithmId] = useState<AlgorithmId>("qpso_hybrid");
  const [values, setValues] = useState<ParamValues | null>(null);
  const [seed, setSeed] = useState("");

  if (algorithms.isPending) return <LoadingState label="Loading algorithms…" />;
  if (algorithms.isError) return <ErrorState error={algorithms.error} />;
  const info = algorithms.data.find((a) => a.id === algorithmId)!;
  const current = values ?? defaultValues(info.params);
  const errors = formErrors(info.params, current);
  const seedValue = seed.trim() === "" ? null : Number(seed);
  const seedInvalid = seedValue !== null && (!Number.isInteger(seedValue) || seedValue < 0);
  const blocked = !versionId || seedInvalid || Object.keys(errors).length > 0 || submit.isPending;

  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (blocked) return;
        submit.mutate(
          {
            scenario_version_id: versionId!,
            algorithm_id: algorithmId,
            config: changedOnly(info.params, current),
            seed: info.uses_seed ? seedValue : null,
          },
          { onSuccess: (run) => setActiveRun(run.id) },
        );
      }}
    >
      <div className="grid gap-1">
        <Label htmlFor="lab-algorithm" className="text-xs">
          Algorithm
        </Label>
        <NativeSelect
          id="lab-algorithm"
          value={algorithmId}
          onChange={(e) => {
            setAlgorithmId(e.target.value as AlgorithmId);
            setValues(null);
          }}
        >
          {algorithms.data.map((a) => (
            <option key={a.id} value={a.id}>
              {ALGORITHM_LABELS[a.id] ?? a.id} · v{a.version}
            </option>
          ))}
        </NativeSelect>
      </div>
      <ParamForm params={info.params} values={current} onChange={setValues} />
      {info.uses_seed ? (
        <div className="grid gap-1">
          <Label htmlFor="lab-seed" className="text-xs">
            Seed <span className="text-text-muted">(blank: generated and recorded by server)</span>
          </Label>
          <Input
            id="lab-seed"
            inputMode="numeric"
            className="num h-8"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            aria-invalid={seedInvalid}
          />
        </div>
      ) : (
        <p className="text-text-muted text-[11px]">This solver takes no seed.</p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={blocked} className="flex-1">
          {submit.isPending ? "Submitting…" : "Submit run"}
        </Button>
        <Button type="button" variant="outline" onClick={() => setValues(null)}>
          Defaults
        </Button>
      </div>
      {submit.isError && (
        <ErrorState
          error={submit.error}
          title={
            submit.error instanceof ApiError ? `Rejected (${submit.error.code})` : "Submit failed"
          }
        />
      )}
      {!versionId && (
        <p className="text-text-muted text-[11px]">
          Load a scenario in the{" "}
          <Link href="/command-center" className="underline">
            Command Center
          </Link>{" "}
          first.
        </p>
      )}
      <p className="text-text-muted text-[11px]">
        Only values changed from the defaults are sent; the run stores the full resolved
        configuration.
      </p>
    </form>
  );
}

function Diagnostics({ result }: { result: RunResultOut }) {
  const entries = Object.entries(result.diagnostics).filter(([k]) => k !== "software");
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
      {entries.map(([k, v]) => {
        let shown: string;
        if (Array.isArray(v)) {
          const nums = v.filter((x): x is number => typeof x === "number");
          shown =
            nums.length === v.length && v.length > 0
              ? `${v.length} values: ${nums[0].toFixed(4)} → ${nums[nums.length - 1].toFixed(4)}`
              : `${v.length} items`;
        } else if (typeof v === "number") {
          shown = Number.isInteger(v) ? String(v) : v.toPrecision(5);
        } else if (v && typeof v === "object") {
          shown = JSON.stringify(v);
        } else {
          shown = String(v);
        }
        return (
          <div key={k} className="contents">
            <dt className="num text-muted-foreground">{k}</dt>
            <dd className="num break-words">{shown}</dd>
          </div>
        );
      })}
    </dl>
  );
}

function Feasibility({ versionId, scenario }: { versionId: string; scenario: ScenarioOut }) {
  const data = useMemo(() => {
    const { id: _id, name: _name, ...rest } = scenario;
    return rest;
  }, [scenario]);
  const v = useValidation(versionId, data);
  if (v.isPending) return <LoadingState label="Checking scenario…" />;
  if (v.isError) return <ErrorState error={v.error} />;
  const d = v.data;
  return (
    <div className="grid gap-2 text-xs">
      <dl className="grid grid-cols-2 gap-2">
        <Stat label="Total demand" value={d.total_demand} digits={0} />
        <Stat label="Fleet capacity" value={d.total_capacity} digits={0} />
        <Stat label="Strong components" value={d.strongly_connected_components} digits={0} />
        <Stat label="Unreachable pairs" value={d.unreachable_location_pairs} digits={0} />
      </dl>
      <p className={cn(d.feasible_so_far ? "text-traffic-normal" : "text-incident")}>
        {d.feasible_so_far
          ? "No infeasibility detected (capacity totals and reachability). Not a proof that a solution exists."
          : "Infeasibility detected: runs will end with infeasible_scenario."}
      </p>
      {d.issues.length > 0 && (
        <ul className="grid gap-0.5">
          {d.issues.map((i, n) => (
            <li key={n}>
              <span className="num">[{i.severity}]</span> {i.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RunDetails({ run, result }: { run: RunOut; result: RunResultOut | undefined }) {
  return (
    <>
      <Section title="Execution statistics">
        {!result ? (
          <EmptyState>Available when the run finishes ({run.status}).</EmptyState>
        ) : (
          <dl className="grid grid-cols-2 gap-2">
            <Stat label="Objective" value={result.objective} unit="min" digits={3} kind="derived" />
            <Stat label="Feasible" value={result.feasible ? "yes" : "no"} />
            <Stat label="Iterations" value={result.iterations} digits={0} />
            <Stat label="Evaluations" value={result.evaluations} digits={0} />
            <Stat label="Wall time" value={result.elapsed_s} unit="s" kind="measured" />
            <Stat
              label="First feasible"
              value={result.time_to_first_feasible_s}
              unit="s"
              kind="measured"
            />
            <Stat label="Stopped" value={result.termination_reason.replace("_", " ")} />
            <Stat
              label="Optimality"
              value={result.optimality === "proven_optimal" ? "proven" : "not proven"}
            />
          </dl>
        )}
      </Section>
      <Section title="Resolved configuration (stored)">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
          <dt className="text-muted-foreground">algorithm</dt>
          <dd className="num">
            {run.algorithm_id} v{run.algorithm_version}
          </dd>
          <dt className="text-muted-foreground">seed</dt>
          <dd className="num">{run.seed ?? "n/a"}</dd>
          {Object.entries(run.config).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="num text-muted-foreground">{k}</dt>
              <dd className="num truncate">{JSON.stringify(v)}</dd>
            </div>
          ))}
        </dl>
      </Section>
      {result && (
        <Section title="Algorithm diagnostics">
          <Diagnostics result={result} />
        </Section>
      )}
    </>
  );
}

export function AlgorithmLab() {
  const versionId = useWorkspace((s) => s.versionId);
  const activeRunId = useWorkspace((s) => s.activeRunId);
  const version = useVersion(versionId);
  const run = useRun(activeRunId);
  const result = useRunResult(run.data);
  const log = useRunEventLog(activeRunId);
  const [axis, setAxis] = useState<XAxis>("iteration");

  const series = useMemo<ConvergenceSeries[]>(() => {
    if (result.data) {
      return [
        {
          name: `${ALGORITHM_LABELS[run.data!.algorithm_id]} (stored history)`,
          source: "stored",
          points: historyToPoints(result.data.history, axis),
        },
      ];
    }
    return [liveSeries(log.events, axis)];
  }, [result.data, run.data, log.events, axis]);

  return (
    <WorkspaceLayout
      left={
        <Section title="Algorithm configuration">
          <ConfigPanel />
        </Section>
      }
      center={
        <div className="flex h-full flex-col gap-2 overflow-y-auto p-4">
          <div className="flex items-center justify-between gap-2">
            <h1 className="text-sm font-semibold">Convergence</h1>
            <div className="flex items-center gap-2 text-xs">
              <Label htmlFor="axis" className="text-xs">
                x-axis
              </Label>
              <NativeSelect
                id="axis"
                className="w-auto"
                value={axis}
                onChange={(e) => setAxis(e.target.value as XAxis)}
              >
                <option value="iteration">iteration</option>
                <option value="elapsed_s">elapsed wall time</option>
              </NativeSelect>
            </div>
          </div>
          {!activeRunId ? (
            <EmptyState>Submit a run to see its best-so-far objective here.</EmptyState>
          ) : (
            <ConvergenceChart
              series={series}
              axis={axis}
              height={320}
              label="Best feasible objective versus progress for the active run"
            />
          )}
          <p className="text-text-muted text-[11px]">
            Solid line: history stored with the result. Dashed: progress reports received live
            (throttled). Points before the first feasible solution are not plotted.
          </p>
          {version.data && (
            <Section
              title={`Feasibility: ${version.data.data.name} v${version.data.version_number}`}
            >
              <Feasibility versionId={version.data.id} scenario={version.data.data} />
            </Section>
          )}
        </div>
      }
      right={
        run.data ? (
          <RunDetails run={run.data} result={result.data} />
        ) : (
          <div className="p-3">
            <EmptyState>No active run.</EmptyState>
          </div>
        )
      }
      bottom={<RunMonitor />}
    />
  );
}
