"use client";

import { ErrorState } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/lib/api/client";
import { useSimulationCommand } from "@/lib/api/hooks";
import type { SimulationState } from "@/lib/api/types";

export const TRAFFIC_FACTORS = [1, 1.5, 2, 3, 5];

/** Incident, closure and traffic commands for one road in the active simulation. */
export function RoadActions({ sim, edgeId }: { sim: SimulationState; edgeId: string }) {
  const incident = useSimulationCommand(
    sim.id,
    (id, v: { kind: "closure" | "slowdown"; factor?: number }) =>
      api.createIncident(id, { edge_ids: [edgeId], ...v }),
  );
  const road = useSimulationCommand(
    sim.id,
    (id, v: { closed?: boolean; traffic_factor?: number }) =>
      api.updateRoad(id, { edge_id: edgeId, ...v }),
  );
  const override = sim.road_overrides.find((o) => o.edge_id === edgeId);
  const manualClosed = sim.manual_closures.includes(edgeId);
  const factor = sim.traffic_factors[edgeId] ?? 1;
  const users = sim.vehicles.filter(
    (v) => v.edge_id === edgeId || v.remaining_edge_ids.includes(edgeId),
  );
  const error = incident.error ?? road.error;
  return (
    <div className="mt-3 grid gap-2 border-t pt-2 text-xs" aria-label="Simulation road actions">
      <p className="font-medium">In the simulation</p>
      <p className="num text-muted-foreground">
        {override
          ? `${override.closed ? "closed" : "open"} · ${override.current_time.toFixed(2)} min (was ${override.original_current_time.toFixed(2)})`
          : "original conditions"}
        {users.length > 0 && ` · planned by ${users.map((v) => v.id).join(", ")}`}
      </p>
      <div className="flex flex-wrap gap-1">
        <Button
          size="xs"
          variant="destructive"
          onClick={() => incident.mutate({ kind: "closure" })}
        >
          Incident: close road
        </Button>
        <Button
          size="xs"
          variant="outline"
          onClick={() => incident.mutate({ kind: "slowdown", factor: 3 })}
        >
          Incident: slow ×3
        </Button>
        <Button size="xs" variant="outline" onClick={() => road.mutate({ closed: !manualClosed })}>
          {manualClosed ? "Reopen road" : "Close road"}
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Label htmlFor="traffic-factor" className="text-xs">
          Traffic factor
        </Label>
        <NativeSelect
          id="traffic-factor"
          className="w-auto"
          value={factor}
          onChange={(e) => road.mutate({ traffic_factor: Number(e.target.value) })}
        >
          {TRAFFIC_FACTORS.map((f) => (
            <option key={f} value={f}>
              ×{f}
            </option>
          ))}
        </NativeSelect>
      </div>
      <p className="text-text-muted text-[11px]">
        A vehicle already on this road keeps its progress; the rest of the road is re-timed.
        Closures stop vehicles from entering; replan to route around them.
      </p>
      {error && <ErrorState error={error} title="Command rejected" />}
    </div>
  );
}
