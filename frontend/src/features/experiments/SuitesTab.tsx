"use client";

import { Download } from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorState, LoadingState, RunStatusBadge, Section } from "@/components/status";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { SeedChart } from "@/components/charts/ConvergenceChart";
import { ALGORITHM_LABELS, BUDGET_PARAMS } from "@/features/command-center/RunLauncher";
import { api } from "@/lib/api/client";
import {
  useAlgorithms,
  useLaunchSuite,
  useRunList,
  useSavedScenarios,
  useSuite,
  useSuiteComparison,
  useSuites,
} from "@/lib/api/hooks";
import type { AlgorithmId, SuiteComparison, SuiteSpec } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const fmt = (v: number | null | undefined, d = 3) => (v == null ? "–" : v.toFixed(d));

export function budgetPolicy(specs: SuiteSpec[]): string {
  return specs
    .map((s) =>
      BUDGET_PARAMS[s.algorithm_id]
        .map((p) => `${s.label ?? s.algorithm_id}: ${p.key}=${String(s.config[p.key])} ${p.unit}`)
        .join(", "),
    )
    .join("; ");
}

function LaunchForm({ onLaunched }: { onLaunched: (id: string) => void }) {
  const scenarios = useSavedScenarios();
  const algorithms = useAlgorithms();
  const launch = useLaunchSuite();
  const [scenarioId, setScenarioId] = useState("");
  const [name, setName] = useState("Baseline comparison");
  const [repetitions, setRepetitions] = useState(3);
  const [enabled, setEnabled] = useState<Record<AlgorithmId, boolean>>({
    ortools_cvrp: true,
    simulated_annealing: true,
    qpso_hybrid: true,
  });
  const [budgets, setBudgets] = useState<Record<string, number>>({});
  if (algorithms.isPending || scenarios.isPending) return <LoadingState label="Loading…" />;
  if (algorithms.isError) return <ErrorState error={algorithms.error} />;
  const versionId = scenarios.data?.items.find((s) => s.id === scenarioId)?.current_version_id;
  const specs: SuiteSpec[] = algorithms.data
    .filter((a) => enabled[a.id])
    .map((a) => ({
      algorithm_id: a.id,
      label: a.id,
      config: Object.fromEntries(
        BUDGET_PARAMS[a.id].map((p) => [
          p.key,
          budgets[`${a.id}.${p.key}`] ?? Number(a.defaults[p.key]),
        ]),
      ),
    }));
  return (
    <form
      className="grid gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!versionId || !specs.length) return;
        launch.mutate(
          {
            name,
            scenario_version_id: versionId,
            specs,
            repetitions,
            budget_policy: budgetPolicy(specs),
          },
          { onSuccess: (s) => onLaunched(s.id) },
        );
      }}
    >
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
        <div className="grid gap-1">
          <Label htmlFor="s-name" className="text-xs">
            Suite name
          </Label>
          <Input
            id="s-name"
            className="h-8"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="s-scenario" className="text-xs">
            Scenario (current version)
          </Label>
          <NativeSelect
            id="s-scenario"
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
          >
            <option value="">Choose…</option>
            {scenarios.data?.items.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="s-reps" className="text-xs">
            Repetitions (seeds 0..n-1)
          </Label>
          <Input
            id="s-reps"
            type="number"
            min={1}
            max={30}
            className="num h-8"
            value={repetitions}
            onChange={(e) => setRepetitions(Number(e.target.value))}
          />
        </div>
      </div>
      <fieldset className="grid gap-1">
        <legend className="text-xs">Algorithms and budgets</legend>
        {algorithms.data.map((a) => (
          <div key={a.id} className="flex flex-wrap items-center gap-3 text-xs">
            <label className="flex w-56 items-center gap-1">
              <input
                type="checkbox"
                className="accent-[var(--tq-signal)]"
                checked={enabled[a.id]}
                onChange={(e) => setEnabled({ ...enabled, [a.id]: e.target.checked })}
              />
              {ALGORITHM_LABELS[a.id]}
            </label>
            {BUDGET_PARAMS[a.id].map((p) => (
              <label key={p.key} className="flex items-center gap-1">
                <span className="num text-muted-foreground">{p.key}</span>
                <Input
                  type="number"
                  className="num h-7 w-24"
                  min={p.min}
                  max={p.max}
                  step={p.step}
                  disabled={!enabled[a.id]}
                  aria-label={`${a.id} ${p.key}`}
                  value={budgets[`${a.id}.${p.key}`] ?? Number(a.defaults[p.key])}
                  onChange={(e) =>
                    setBudgets({ ...budgets, [`${a.id}.${p.key}`]: Number(e.target.value) })
                  }
                />
                <span className="text-muted-foreground">{p.unit}</span>
              </label>
            ))}
          </div>
        ))}
      </fieldset>
      <p className="text-muted-foreground text-[11px]">
        Budgets are in different units per algorithm (recorded as the suite&apos;s budget policy).
        Runs: {specs.length} × {repetitions} = {specs.length * repetitions}.
      </p>
      {launch.isError && <ErrorState error={launch.error} title="Launch rejected" />}
      <Button
        type="submit"
        disabled={!versionId || !specs.length || launch.isPending}
        className="w-fit"
      >
        {launch.isPending ? "Launching…" : "Launch suite"}
      </Button>
    </form>
  );
}

function ComparisonTable({ c }: { c: SuiteComparison }) {
  const ref = c.reference;
  return (
    <div className="grid gap-2">
      <p className="text-xs">
        {ref ? (
          <>
            Gap reference:{" "}
            <strong>
              {ref.kind === "proven_optimum"
                ? "proven optimum"
                : "best observed heuristic (not an optimum)"}
            </strong>{" "}
            = <span className="num">{ref.objective.toFixed(3)} min</span> (from {ref.source_spec},
            seed {ref.source_seed ?? "n/a"}).
          </>
        ) : (
          "No feasible completed run yet: no reference, no gaps."
        )}{" "}
        Statistics use COMPLETED runs only; cancelled, failed and unfinished runs are counted, never
        imputed.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs" aria-label="Suite statistics">
          <thead className="text-muted-foreground">
            <tr>
              {[
                "Spec",
                "n",
                "Feasible",
                "Mean",
                "Median",
                "Std (n−1)",
                "Best",
                "Worst",
                "Gap % (mean)",
                "Wall time mean (s, measured)",
                "Statuses",
              ].map((h) => (
                <th key={h} scope="col" className="py-1 pr-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {c.summaries.map((s) => (
              <tr key={s.spec} className="border-t">
                <th scope="row" className="py-1 pr-3 font-normal">
                  {s.spec}
                </th>
                <td className="num pr-3">{s.n}</td>
                <td className="num pr-3">{s.n ? `${s.feasible_count}/${s.n}` : "–"}</td>
                <td className="num pr-3">{fmt(s.objective_mean)}</td>
                <td className="num pr-3">{fmt(s.objective_median)}</td>
                <td className="num pr-3">{fmt(s.objective_std)}</td>
                <td className="num pr-3">{fmt(s.objective_best)}</td>
                <td className="num pr-3">{fmt(s.objective_worst)}</td>
                <td className="num pr-3">{fmt(s.gap_mean_percent, 2)}</td>
                <td className="num pr-3">{s.n ? fmt(s.elapsed_mean_s, 2) : "–"}</td>
                <td className="num">
                  {Object.entries(c.status_counts_by_spec[s.spec] ?? {})
                    .map(([k, v]) => `${k}:${v}`)
                    .join(" ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-muted-foreground text-[11px]">
        Objective statistics in minutes (derived by the shared evaluator).
      </p>
    </div>
  );
}

function SuiteDetail({ id }: { id: string }) {
  const suite = useSuite(id);
  const revision = JSON.stringify(suite.data?.status_counts ?? {});
  const comparison = useSuiteComparison(id, revision);
  const runs = useRunList({ suite_id: id, limit: 100 });
  if (suite.isPending) return <LoadingState label="Loading suite…" />;
  if (suite.isError) return <ErrorState error={suite.error} />;
  const s = suite.data;
  const total = s.run_ids.length;
  const done =
    (s.status_counts.COMPLETED ?? 0) +
    (s.status_counts.CANCELLED ?? 0) +
    (s.status_counts.FAILED ?? 0);
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="font-semibold">{s.name}</span>
        <span className="num text-muted-foreground">
          {done}/{total} runs finished
        </span>
        <span className="num text-muted-foreground">seeds {s.seeds.join(", ")}</span>
        <a
          className={cn(buttonVariants({ size: "xs", variant: "outline" }), "ml-auto")}
          href={api.suiteExportUrl(s.id, "csv")}
          download
        >
          <Download aria-hidden="true" /> Export CSV
        </a>
        <a
          className={buttonVariants({ size: "xs", variant: "outline" })}
          href={api.suiteExportUrl(s.id, "json")}
          download
        >
          <Download aria-hidden="true" /> Export JSON
        </a>
      </div>
      <p className="text-muted-foreground text-[11px]">
        Budget policy: {s.budget_policy || "not recorded"}
      </p>
      {comparison.isError && <ErrorState error={comparison.error} />}
      {comparison.data && <ComparisonTable c={comparison.data} />}
      {comparison.data && (
        <div>
          <h3 className="text-xs font-semibold">Objective by seed (completed runs)</h3>
          <SeedChart
            runs={comparison.data.runs ?? []}
            specs={s.specs.map((x) => x.label)}
            label="Objective of each completed run by algorithm spec, with spec means"
          />
          <p className="text-muted-foreground text-[11px]">
            Each point is one stored run; dashed lines are spec means. Infeasible, cancelled and
            failed runs are not plotted (see statuses).
          </p>
        </div>
      )}
      <h3 className="text-xs font-semibold">Seed-level runs</h3>
      {runs.data && (
        <table className="w-full text-left text-xs" aria-label="Seed-level runs">
          <thead className="text-muted-foreground">
            <tr>
              <th scope="col" className="py-1 pr-3 font-normal">
                Spec
              </th>
              <th scope="col" className="pr-3 font-normal">
                Repetition
              </th>
              <th scope="col" className="pr-3 font-normal">
                Seed
              </th>
              <th scope="col" className="pr-3 font-normal">
                Status
              </th>
              <th scope="col" className="font-normal">
                Run
              </th>
            </tr>
          </thead>
          <tbody>
            {[...runs.data.items]
              .sort(
                (a, b) =>
                  (a.suite_spec ?? "").localeCompare(b.suite_spec ?? "") ||
                  (a.repetition ?? 0) - (b.repetition ?? 0),
              )
              .map((r) => (
                <tr key={r.id} className="border-t">
                  <td className="py-1 pr-3">{r.suite_spec}</td>
                  <td className="num pr-3">{r.repetition}</td>
                  <td className="num pr-3">{r.seed ?? "n/a"}</td>
                  <td className="pr-3">
                    <RunStatusBadge status={r.status} />
                  </td>
                  <td className="num">{r.id.slice(0, 8)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function SuitesTab() {
  const suites = useSuites();
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="grid gap-4">
      <Section title="Launch a benchmark suite">
        <LaunchForm onLaunched={setSelected} />
      </Section>
      <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <Section title="Suites">
          {suites.isPending && <LoadingState label="Loading suites…" />}
          {suites.isError && <ErrorState error={suites.error} />}
          {suites.data?.items.length === 0 && <EmptyState>No suites yet.</EmptyState>}
          <ul className="grid gap-0.5">
            {suites.data?.items.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => setSelected(s.id)}
                  aria-pressed={selected === s.id}
                  className={cn(
                    "w-full rounded-sm px-2 py-1 text-left text-xs",
                    selected === s.id ? "bg-secondary" : "hover:bg-secondary/60",
                  )}
                >
                  <span className="block truncate">{s.name}</span>
                  <span className="num text-muted-foreground">
                    {new Date(s.created_at).toLocaleString()} · {s.run_ids.length} runs
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Suite comparison">
          {selected ? (
            <SuiteDetail id={selected} />
          ) : (
            <EmptyState>Select or launch a suite.</EmptyState>
          )}
        </Section>
      </div>
    </div>
  );
}
