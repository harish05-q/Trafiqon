"use client";

import { Pause, Play, RotateCcw, Route, SkipForward, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, Section, Stat } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/lib/api/client";
import { useSimulation, useSimulationCommand } from "@/lib/api/hooks";
import type { RunOut, SimAction, SimulationState } from "@/lib/api/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/stores/workspace";
import { formatSimTime } from "./simView";

function Controls({ sim }: { sim: SimulationState }) {
  const control = useSimulationCommand(
    sim.id,
    (id, v: { action: SimAction; ticks?: number; speed?: number }) => api.controlSimulation(id, v),
  );
  const replan = useSimulationCommand(sim.id, (id) => api.replanSimulation(id));
  const resolve = useSimulationCommand(sim.id, (id, incidentId: string) =>
    api.resolveIncident(id, incidentId),
  );
  const busy = control.isPending || replan.isPending;
  const go = (action: SimAction, extra: { ticks?: number; speed?: number } = {}) =>
    control.mutate({ action, ...extra });
  const report = sim.last_replan;
  const active = sim.incidents.filter((i) => i.active);
  return (
    <div className="grid gap-3">
      <dl className="grid grid-cols-3 gap-2">
        <Stat label="Sim clock" value={formatSimTime(sim.time_min)} />
        <Stat label="Status" value={sim.status} />
        <Stat label="Served" value={`${sim.served_count}/${sim.customer_count}`} />
      </dl>
      <div className="flex flex-wrap gap-1" role="toolbar" aria-label="Simulation controls">
        {sim.status === "ready" && (
          <Button size="sm" onClick={() => go("start")} disabled={busy}>
            <Play /> Start
          </Button>
        )}
        {sim.status === "running" && (
          <Button size="sm" variant="outline" onClick={() => go("pause")} disabled={busy}>
            <Pause /> Pause
          </Button>
        )}
        {sim.status === "paused" && (
          <Button size="sm" onClick={() => go("resume")} disabled={busy}>
            <Play /> Resume
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() => go("step", { ticks: 1 })}
          disabled={busy || sim.status === "running" || sim.status === "finished"}
          title={`Advance one tick (${sim.tick_minutes} simulated min)`}
        >
          <SkipForward /> Step
        </Button>
        <Button size="sm" variant="outline" onClick={() => go("reset")} disabled={busy}>
          <RotateCcw /> Reset
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => replan.mutate(undefined)}
          disabled={busy}
        >
          <Route /> Replan
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Label htmlFor="sim-speed" className="text-xs">
          Speed
        </Label>
        <NativeSelect
          id="sim-speed"
          className="w-auto"
          value={sim.speed}
          onChange={(e) => go("speed", { speed: Number(e.target.value) })}
        >
          {sim.speeds.map((s) => (
            <option key={s} value={s}>
              {s} sim min / s
            </option>
          ))}
        </NativeSelect>
        <span className="num text-text-muted text-[11px]">
          tick {sim.tick} · plan v{sim.plan_version}
        </span>
      </div>
      {(control.isError || replan.isError) && (
        <ErrorState error={(control.error ?? replan.error)!} title="Command rejected" />
      )}
      {report && (
        <div className="text-xs" aria-label="Last replan">
          <p className="font-medium">
            Replan v{report.plan_version} at {formatSimTime(report.time)}
          </p>
          <p className="num text-muted-foreground">
            latency {report.latency_ms.toFixed(2)} ms (measured) · {report.stops_reordered} stops
            reordered · {report.edges_changed} road segments changed
          </p>
          {report.unserved.length > 0 && (
            <p className="text-incident">Unreachable, not served: {report.unserved.join(", ")}</p>
          )}
          {report.vehicles
            .filter((v) => !v.end_depot_reachable)
            .map((v) => (
              <p key={v.vehicle_id} className="text-incident">
                {v.vehicle_id} cannot reach its end depot: stranded until roads reopen.
              </p>
            ))}
        </div>
      )}
      <div>
        <h3 className="mb-1 text-xs font-semibold">Incidents ({active.length} active)</h3>
        {sim.incidents.length === 0 ? (
          <EmptyState>Select a road on the map to create an incident.</EmptyState>
        ) : (
          <ul className="grid gap-1 text-xs" aria-label="Incidents">
            {sim.incidents.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-2">
                <span className={i.active ? "text-incident" : "text-text-muted line-through"}>
                  <span className="num">{i.id}</span> {i.kind}
                  {i.kind === "slowdown" && ` ×${i.factor}`} · {i.edge_ids.join(", ")}
                </span>
                {i.active && (
                  <Button size="xs" variant="outline" onClick={() => resolve.mutate(i.id)}>
                    Resolve
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="text-text-muted text-[11px]">
        Simulated quantities (clock, positions, driving time) come from the backend engine; the map
        only interpolates between its updates. Replanning keeps positions, completed stops and the
        clock, and reorders each vehicle&apos;s own remaining stops.
      </p>
    </div>
  );
}

export function SimulationPanel({
  run,
  versionId,
}: {
  run: RunOut | undefined;
  versionId: string;
}) {
  const simulationId = useWorkspace((s) => s.simulationId);
  const setSimulation = useWorkspace((s) => s.setSimulation);
  const sim = useSimulation(simulationId);
  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: (fromRun: boolean) =>
      api.createSimulation({ scenario_version_id: versionId, run_id: fromRun ? run!.id : null }),
    onSuccess: (state) => {
      qc.setQueryData(["simulations", state.id], state);
      setSimulation(state.id);
    },
  });
  const runUsable = run?.status === "COMPLETED";
  const stale = sim.isError || (sim.data && sim.data.scenario_version_id !== versionId);

  return (
    <Section
      title="Simulation"
      actions={
        simulationId && (
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Close simulation"
            onClick={() => {
              api.deleteSimulation(simulationId).catch(() => undefined);
              setSimulation(null);
            }}
          >
            <Trash2 />
          </Button>
        )
      }
    >
      {(!simulationId || stale) && (
        <div className="grid gap-2">
          {sim.isError && (
            <EmptyState>
              The previous session is gone (sessions are not kept across API restarts).
            </EmptyState>
          )}
          <Button
            size="sm"
            disabled={!runUsable || create.isPending}
            onClick={() => create.mutate(true)}
          >
            Simulate the active run&apos;s solution
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={create.isPending}
            onClick={() => create.mutate(false)}
          >
            Simulate a construction plan
          </Button>
          {!runUsable && (
            <p className="text-text-muted text-[11px]">
              Complete a run on this version to simulate its routes.
            </p>
          )}
          {create.isError && (
            <ErrorState error={create.error} title="Could not start a simulation" />
          )}
        </div>
      )}
      {sim.data && !stale && <Controls sim={sim.data} />}
    </Section>
  );
}
