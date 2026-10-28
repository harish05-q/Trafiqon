"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorState, LoadingState, Section } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ApiError } from "@/lib/api/client";
import { useAlgorithms, useSubmitRun } from "@/lib/api/hooks";
import type { AlgorithmId, AlgorithmInfo } from "@/lib/api/types";
import { useWorkspace } from "@/stores/workspace";

/** The budget parameters exposed here; every other setting uses the server default
 * (shown in the Algorithm Lab, M6). Descriptions match docs/algorithms.md. */
export const BUDGET_PARAMS: Record<
  AlgorithmId,
  {
    key: string;
    label: string;
    unit: string;
    min: number;
    max: number;
    step: number;
    help: string;
  }[]
> = {
  ortools_cvrp: [
    {
      key: "time_limit_s",
      label: "Time limit",
      unit: "s",
      min: 0.1,
      max: 120,
      step: 0.1,
      help: "Wall-clock limit for guided local search. Results are not proven optimal.",
    },
  ],
  simulated_annealing: [
    {
      key: "max_iterations",
      label: "Iterations",
      unit: "moves",
      min: 1000,
      max: 2_000_000,
      step: 1000,
      help: "Proposed moves; the temperature reaches 0.1% of T0 at the limit. Deterministic per seed.",
    },
  ],
  qpso_hybrid: [
    {
      key: "iterations",
      label: "Iterations",
      unit: "updates",
      min: 1,
      max: 2000,
      step: 1,
      help: "Swarm updates. Each update decodes, repairs and locally improves every particle.",
    },
    {
      key: "swarm_size",
      label: "Swarm size",
      unit: "particles",
      min: 2,
      max: 100,
      step: 1,
      help: "Particles per iteration (budget = swarm size × iterations).",
    },
  ],
};

export const ALGORITHM_LABELS: Record<AlgorithmId, string> = {
  ortools_cvrp: "OR-Tools CVRP (reference)",
  simulated_annealing: "Simulated Annealing",
  qpso_hybrid: "QPSO-inspired hybrid",
};

function budgetDefaults(info: AlgorithmInfo | undefined): Record<string, number> {
  if (!info) return {};
  return Object.fromEntries(
    BUDGET_PARAMS[info.id].map((p) => [p.key, Number(info.defaults[p.key])]),
  );
}

export function RunLauncher() {
  const algorithms = useAlgorithms();
  const versionId = useWorkspace((s) => s.versionId);
  const setActiveRun = useWorkspace((s) => s.setActiveRun);
  const submit = useSubmitRun();
  const [algorithmId, setAlgorithmId] = useState<AlgorithmId>("qpso_hybrid");
  const [budget, setBudget] = useState<Record<string, number> | null>(null);
  const [seed, setSeed] = useState("");

  const info = algorithms.data?.find((a) => a.id === algorithmId);
  const values = budget ?? budgetDefaults(info);
  const seedValue = seed.trim() === "" ? null : Number(seed);
  const seedInvalid = seedValue !== null && (!Number.isInteger(seedValue) || seedValue < 0);

  return (
    <Section title="Optimization run">
      {algorithms.isPending && <LoadingState label="Loading algorithms…" />}
      {algorithms.isError && <ErrorState error={algorithms.error} />}
      {algorithms.data && (
        <form
          className="grid gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!versionId || seedInvalid) return;
            submit.mutate(
              {
                scenario_version_id: versionId,
                algorithm_id: algorithmId,
                config: values,
                seed: seedValue,
              },
              { onSuccess: (run) => setActiveRun(run.id) },
            );
          }}
        >
          <div className="grid gap-1">
            <Label htmlFor="algorithm" className="text-xs">
              Algorithm
            </Label>
            <NativeSelect
              id="algorithm"
              value={algorithmId}
              onChange={(e) => {
                setAlgorithmId(e.target.value as AlgorithmId);
                setBudget(null);
              }}
            >
              {algorithms.data.map((a) => (
                <option key={a.id} value={a.id}>
                  {ALGORITHM_LABELS[a.id] ?? a.id} · v{a.version}
                </option>
              ))}
            </NativeSelect>
          </div>
          {info &&
            BUDGET_PARAMS[info.id].map((p) => (
              <div key={p.key} className="grid gap-1">
                <Label htmlFor={`budget-${p.key}`} className="text-xs">
                  {p.label} <span className="text-muted-foreground">({p.unit})</span>
                </Label>
                <Input
                  id={`budget-${p.key}`}
                  type="number"
                  className="num h-8"
                  min={p.min}
                  max={p.max}
                  step={p.step}
                  value={Number.isFinite(values[p.key]) ? values[p.key] : ""}
                  onChange={(e) => setBudget({ ...values, [p.key]: Number(e.target.value) })}
                  aria-describedby={`budget-${p.key}-help`}
                />
                <p id={`budget-${p.key}-help`} className="text-muted-foreground text-[11px]">
                  {p.help}
                </p>
              </div>
            ))}
          {info?.uses_seed && (
            <div className="grid gap-1">
              <Label htmlFor="seed" className="text-xs">
                Seed{" "}
                <span className="text-muted-foreground">
                  (blank: server generates and records one)
                </span>
              </Label>
              <Input
                id="seed"
                inputMode="numeric"
                className="num h-8"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                aria-invalid={seedInvalid}
              />
            </div>
          )}
          {info && !info.uses_seed && (
            <p className="text-muted-foreground text-[11px]">This solver takes no seed.</p>
          )}
          {submit.isError && (
            <ErrorState
              error={submit.error}
              title={
                submit.error instanceof ApiError
                  ? `Rejected (${submit.error.code})`
                  : "Submit failed"
              }
            />
          )}
          <Button type="submit" disabled={!versionId || seedInvalid || submit.isPending}>
            {submit.isPending ? "Submitting…" : "Launch run"}
          </Button>
          {!versionId && (
            <p className="text-muted-foreground text-[11px]">Load a scenario first.</p>
          )}
          <p className="text-muted-foreground text-[11px]">
            Budget only here; every parameter is in the{" "}
            <Link href="/algorithm-lab" className="underline">
              Algorithm Lab
            </Link>
            .
          </p>
        </form>
      )}
    </Section>
  );
}
