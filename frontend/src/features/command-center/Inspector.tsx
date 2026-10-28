"use client";

import { EmptyState, ErrorState, LoadingState, Section, Stat } from "@/components/status";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { trafficState } from "@/features/network/toFlow";
import { useRuns } from "@/lib/api/hooks";
import { ALGORITHM_LABELS } from "./RunLauncher";
import type { RunOut, RunResultOut, ScenarioOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { useWorkspace, type Selection } from "@/stores/workspace";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="num min-w-0 truncate">{v}</dd>
    </>
  );
}

function SelectionDetails({
  selection,
  scenario,
  result,
}: {
  selection: Selection;
  scenario: ScenarioOut;
  result: RunResultOut | undefined;
}) {
  if (!selection) return <EmptyState>Select a road, node or route to inspect it.</EmptyState>;
  const routes = result?.evaluation?.routes ?? [];

  if (selection.kind === "edge") {
    const e = scenario.graph.edges.find((x) => x.id === selection.id);
    if (!e) return <EmptyState>Road not in this version.</EmptyState>;
    const traffic = trafficState(e);
    const users = routes.filter((r) => r.legs.some((l) => l.edge_ids.includes(e.id)));
    return (
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <Row k="Road" v={e.id} />
        <Row k="Direction" v={`${e.source} → ${e.target}`} />
        <Row k="Current time" v={`${e.current_time.toFixed(2)} min`} />
        <Row k="Base time" v={`${e.base_time.toFixed(2)} min`} />
        <Row k="Distance" v={`${e.distance.toFixed(3)} km`} />
        <Row k="Class" v={e.road_class ?? "–"} />
        <Row
          k="Status"
          v={
            <span
              className={cn(
                traffic === "closed" && "text-incident",
                traffic === "congested" && "text-traffic-congested",
              )}
            >
              {traffic}
              {e.congestion != null && ` (×${e.congestion})`}
            </span>
          }
        />
        <Row k="On routes" v={users.length ? users.map((r) => r.vehicle_id).join(", ") : "none"} />
      </dl>
    );
  }

  if (selection.kind === "node") {
    const n = scenario.graph.nodes.find((x) => x.id === selection.id);
    if (!n) return <EmptyState>Node not in this version.</EmptyState>;
    const depot = scenario.depots.find((d) => d.node_id === n.id);
    const customer = scenario.customers.find((c) => c.node_id === n.id);
    const out = scenario.graph.edges.filter((e) => e.source === n.id);
    const inn = scenario.graph.edges.filter((e) => e.target === n.id);
    const servedBy = customer && routes.find((r) => r.customer_ids.includes(customer.id));
    return (
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <Row k="Node" v={n.id} />
        <Row
          k="Type"
          v={depot ? `depot ${depot.id}` : customer ? `customer ${customer.id}` : "intersection"}
        />
        {customer && <Row k="Demand" v={customer.demand} />}
        {customer && <Row k="Served by" v={servedBy?.vehicle_id ?? (result ? "–" : "no result")} />}
        <Row
          k="Outgoing roads"
          v={`${out.length} (${out.filter((e) => e.closed).length} closed)`}
        />
        <Row
          k="Incoming roads"
          v={`${inn.length} (${inn.filter((e) => e.closed).length} closed)`}
        />
        <Row k="Coordinates" v={`${n.x ?? "–"}, ${n.y ?? "–"} (synthetic units)`} />
      </dl>
    );
  }

  const r = routes.find((x) => x.vehicle_id === selection.vehicleId);
  if (!r) return <EmptyState>Route not in the current result.</EmptyState>;
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
      <Row k="Vehicle" v={r.vehicle_id} />
      <Row k="Stops" v={r.customer_ids.join(" → ") || "none"} />
      <Row k="Load" v={`${r.load} / ${r.capacity ?? "?"}`} />
      <Row k="Travel time" v={r.travel_time == null ? "–" : `${r.travel_time.toFixed(3)} min`} />
      <Row k="Distance" v={r.distance == null ? "–" : `${r.distance.toFixed(3)} km`} />
      <Row k="Road segments" v={r.legs.reduce((n, l) => n + l.edge_ids.length, 0)} />
    </dl>
  );
}

export function Inspector({
  scenario,
  run,
  result,
  resultLoading,
  resultError,
  compareRun,
  compareResult,
}: {
  scenario: ScenarioOut;
  run: RunOut | undefined;
  result: RunResultOut | undefined;
  resultLoading: boolean;
  resultError: Error | null;
  compareRun?: RunOut;
  compareResult?: RunResultOut;
}) {
  const selection = useWorkspace((s) => s.selection);
  const select = useWorkspace((s) => s.select);
  return (
    <>
      <Section title="Inspector">
        <SelectionDetails selection={selection} scenario={scenario} result={result} />
      </Section>
      <Section title="Best solution">
        {!run && <EmptyState>No active run.</EmptyState>}
        {run && !result && !resultLoading && !resultError && (
          <EmptyState>
            {run.status === "FAILED" || (run.status === "CANCELLED" && !run.started_at)
              ? "This run produced no result."
              : "Available when the run finishes."}
          </EmptyState>
        )}
        {resultLoading && <LoadingState label="Loading result…" />}
        {resultError && <ErrorState error={resultError} />}
        {result && (
          <div className="grid gap-2">
            <dl className="grid grid-cols-2 gap-2">
              <Stat
                label="Objective"
                value={result.objective}
                unit="min"
                digits={3}
                kind="derived"
              />
              <Stat
                label="Distance"
                value={result.total_distance}
                unit="km"
                digits={3}
                kind="derived"
              />
              <Stat label="Iterations" value={result.iterations} digits={0} />
              <Stat label="Evaluations" value={result.evaluations} digits={0} />
              <Stat label="Wall time" value={result.elapsed_s} unit="s" kind="measured" />
              <Stat
                label="First feasible"
                value={result.time_to_first_feasible_s}
                unit="s"
                kind="measured"
              />
            </dl>
            <p className="text-xs">
              {result.feasible ? "Feasible" : "Infeasible"} · stopped:{" "}
              {result.termination_reason.replace("_", " ")} ·{" "}
              {result.optimality === "proven_optimal" ? "proven optimal" : "not proven optimal"}
            </p>
            <ul className="grid gap-0.5" aria-label="Vehicle routes">
              {result.evaluation?.routes.map((r) => (
                <li key={r.vehicle_id}>
                  <button
                    type="button"
                    onClick={() => select({ kind: "route", vehicleId: r.vehicle_id })}
                    aria-pressed={
                      selection?.kind === "route" && selection.vehicleId === r.vehicle_id
                    }
                    className={cn(
                      "flex w-full justify-between gap-2 rounded-sm px-2 py-1 text-left text-xs",
                      selection?.kind === "route" && selection.vehicleId === r.vehicle_id
                        ? "bg-secondary shadow-[inset_2px_0_0_var(--tq-route)]"
                        : "hover:bg-secondary/60",
                    )}
                  >
                    <span>
                      {r.vehicle_id} · {r.customer_ids.length} stops
                    </span>
                    <span className="num text-muted-foreground">
                      {r.travel_time?.toFixed(2)} min · {r.load}/{r.capacity}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>
      {run && result && (
        <CompareSection
          run={run}
          result={result}
          compareRun={compareRun}
          compareResult={compareResult}
        />
      )}
    </>
  );
}

/** Current (active) solution versus another completed run on the same scenario version. */
function CompareSection({
  run,
  result,
  compareRun,
  compareResult,
}: {
  run: RunOut;
  result: RunResultOut;
  compareRun?: RunOut;
  compareResult?: RunResultOut;
}) {
  const runs = useRuns(run.scenario_version_id);
  const compareRunId = useWorkspace((s) => s.compareRunId);
  const setCompareRun = useWorkspace((s) => s.setCompareRun);
  const options = (runs.data?.items ?? []).filter(
    (r) => r.id !== run.id && r.status === "COMPLETED",
  );
  const delta =
    compareResult?.objective != null && result.objective != null
      ? result.objective - compareResult.objective
      : null;
  return (
    <Section title="Compare routes">
      <div className="grid gap-2 text-xs">
        <Label htmlFor="compare-run" className="text-xs">
          Compare with another completed run on this version
        </Label>
        <NativeSelect
          id="compare-run"
          value={compareRunId ?? ""}
          onChange={(e) => setCompareRun(e.target.value || null)}
        >
          <option value="">None</option>
          {options.map((r) => (
            <option key={r.id} value={r.id}>
              {ALGORITHM_LABELS[r.algorithm_id] ?? r.algorithm_id} · seed {r.seed ?? "n/a"} ·{" "}
              {r.id.slice(0, 6)}
            </option>
          ))}
        </NativeSelect>
        {compareRun && compareResult && (
          <dl className="grid grid-cols-2 gap-2">
            <Stat label="This run" value={result.objective} unit="min" digits={3} kind="derived" />
            <Stat
              label="Comparison"
              value={compareResult.objective}
              unit="min"
              digits={3}
              kind="derived"
            />
            <Stat
              label="Difference"
              value={delta === null ? null : `${delta > 0 ? "+" : ""}${delta.toFixed(3)}`}
              unit="min"
            />
            <Stat
              label="Vehicles used"
              value={`${result.evaluation?.routes.length ?? 0} vs ${compareResult.evaluation?.routes.length ?? 0}`}
            />
          </dl>
        )}
        {compareRun && (
          <p className="text-text-muted text-[11px]">
            Comparison routes are drawn dotted on the map.
          </p>
        )}
      </div>
    </Section>
  );
}
