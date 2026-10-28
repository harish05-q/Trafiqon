"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { NetworkView } from "@/features/network/NetworkView";
import { api } from "@/lib/api/client";
import type { Algorithm, ScenarioOut, ShortestPathResponse } from "@/lib/api/types";

const EMPTY: readonly string[] = [];

function fmt(n: number, digits = 2) {
  return n.toFixed(digits);
}

export function RouteSlice() {
  const scenarios = useQuery({
    queryKey: ["scenarios", "builtin"],
    queryFn: api.listBuiltinScenarios,
  });
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const activeId = scenarioId ?? scenarios.data?.[0]?.id ?? null;

  const scenario = useQuery({
    queryKey: ["scenarios", "builtin", activeId],
    queryFn: () => api.getBuiltinScenario(activeId!),
    enabled: activeId !== null,
  });

  const [source, setSource] = useState<string | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [algorithm, setAlgorithm] = useState<Algorithm>("dijkstra");
  const route = useMutation({ mutationFn: api.shortestPath });

  const s = scenario.data;
  const src = source ?? s?.depots[0]?.node_id ?? null;
  const dst = target ?? s?.customers[0]?.node_id ?? null;
  const result: ShortestPathResponse | undefined =
    route.data && route.data.scenario_id === s?.id ? route.data : undefined;

  function changeInputs(fn: () => void) {
    route.reset();
    fn();
  }

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center gap-4 border-b border-border bg-surface px-4 py-2">
        <span className="font-semibold tracking-wide">TRAFIQON</span>
        <span className="text-sm text-muted">Route slice</span>
        {s?.synthetic && (
          <span className="rounded border border-border px-2 py-0.5 text-xs text-secondary">
            Synthetic scenario: not real geography
          </span>
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-72 shrink-0 flex-col gap-4 overflow-y-auto border-r border-border bg-surface p-4">
          {scenarios.isError && <ErrorNote error={scenarios.error} />}
          <Field label="Scenario" htmlFor="scenario">
            <select
              id="scenario"
              className="control"
              value={activeId ?? ""}
              disabled={!scenarios.data}
              onChange={(e) =>
                changeInputs(() => {
                  setScenarioId(e.target.value);
                  setSource(null);
                  setTarget(null);
                })
              }
            >
              {scenarios.data?.map((sc) => (
                <option key={sc.id} value={sc.id}>
                  {sc.name} ({sc.node_count} nodes)
                </option>
              ))}
            </select>
          </Field>
          {s && (
            <>
              <NodeSelect
                id="source"
                label="From"
                scenario={s}
                value={src}
                onChange={(v) => changeInputs(() => setSource(v))}
              />
              <NodeSelect
                id="target"
                label="To (or click a node)"
                scenario={s}
                value={dst}
                onChange={(v) => changeInputs(() => setTarget(v))}
              />
              <Field label="Algorithm" htmlFor="algorithm">
                <select
                  id="algorithm"
                  className="control"
                  value={algorithm}
                  onChange={(e) => changeInputs(() => setAlgorithm(e.target.value as Algorithm))}
                >
                  <option value="dijkstra">Dijkstra</option>
                  <option value="astar">A* (straight-line bound)</option>
                </select>
              </Field>
              <button
                type="button"
                className="rounded bg-accent px-3 py-2 font-medium text-background disabled:opacity-60"
                disabled={!src || !dst || route.isPending}
                onClick={() =>
                  route.mutate({ scenario_id: s.id, source: src!, target: dst!, algorithm })
                }
              >
                {route.isPending ? "Computing…" : "Compute route"}
              </button>
              <p className="text-xs text-muted">
                Cost is current travel time. Closed roads are dashed and never used.
              </p>
            </>
          )}
        </aside>

        <main className="relative min-w-0 flex-1">
          {scenario.isPending && activeId && <Centered>Loading scenario…</Centered>}
          {scenario.isError && (
            <Centered>
              <ErrorNote error={scenario.error} />
            </Centered>
          )}
          {s && (
            <NetworkView
              scenario={s}
              pathEdgeIds={result?.path?.edge_ids ?? EMPTY}
              endpoints={[src, dst].filter((x): x is string => x !== null)}
              onNodeClick={(id) => changeInputs(() => setTarget(id))}
            />
          )}
        </main>

        <aside
          className="w-80 shrink-0 overflow-y-auto border-l border-border bg-surface p-4"
          aria-live="polite"
        >
          <h2 className="mb-3 text-sm font-semibold">Route</h2>
          {route.isError && <ErrorNote error={route.error} />}
          {!result && !route.isError && (
            <p className="text-sm text-muted">Pick two nodes and compute a route.</p>
          )}
          {result && !result.reachable && (
            <p className="text-sm text-incident" role="status">
              Unreachable: no open path from {result.source} to {result.target}.
            </p>
          )}
          {result?.path && s && <RouteDetails result={result} scenario={s} />}
        </aside>
      </div>
    </div>
  );
}

function RouteDetails({
  result,
  scenario,
}: {
  result: ShortestPathResponse;
  scenario: ScenarioOut;
}) {
  const path = result.path!;
  const edges = new Map(scenario.graph.edges.map((e) => [e.id, e]));
  return (
    <div className="flex flex-col gap-3 text-sm">
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono tabular-nums">
        <dt className="font-sans text-secondary">Travel time</dt>
        <dd data-testid="travel-time">{fmt(path.travel_time)} min</dd>
        <dt className="font-sans text-secondary">Distance</dt>
        <dd>{fmt(path.distance, 3)} km</dd>
        <dt className="font-sans text-secondary">Road segments</dt>
        <dd>{path.edge_ids.length}</dd>
        <dt className="font-sans text-secondary">Nodes expanded</dt>
        <dd>{result.expanded_nodes}</dd>
        <dt className="font-sans text-secondary">Algorithm</dt>
        <dd>{result.algorithm}</dd>
        <dt className="font-sans text-secondary">Evaluator</dt>
        <dd>v{result.evaluator_version}</dd>
      </dl>
      <ol
        className="flex flex-col gap-0.5 font-mono text-xs"
        aria-label="Route segments"
        data-testid="route-edges"
      >
        {path.edge_ids.map((id) => (
          <li key={id} data-edge-id={id} className="flex justify-between gap-2">
            <span>{id}</span>
            <span className="tabular-nums text-secondary">
              {fmt(edges.get(id)?.current_time ?? NaN)} min
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function NodeSelect(props: {
  id: string;
  label: string;
  scenario: ScenarioOut;
  value: string | null;
  onChange: (v: string) => void;
}) {
  const depots = new Map(props.scenario.depots.map((d) => [d.node_id, d.id]));
  const customers = new Map(props.scenario.customers.map((c) => [c.node_id, c.id]));
  return (
    <Field label={props.label} htmlFor={props.id}>
      <select
        id={props.id}
        className="control"
        value={props.value ?? ""}
        onChange={(e) => props.onChange(e.target.value)}
      >
        {props.scenario.graph.nodes.map((n) => {
          const tag = depots.get(n.id) ?? customers.get(n.id);
          return (
            <option key={n.id} value={n.id}>
              {n.id}
              {tag ? ` (${tag})` : ""}
            </option>
          );
        })}
      </select>
    </Field>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-xs text-secondary">
        {label}
      </label>
      {children}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center text-sm text-muted">
      {children}
    </div>
  );
}

function ErrorNote({ error }: { error: Error }) {
  return (
    <p role="alert" className="rounded border border-incident px-2 py-1 text-sm text-incident">
      {error.message}
    </p>
  );
}
