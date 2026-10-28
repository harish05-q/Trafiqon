"use client";

import { useMemo } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/status";
import { WorkspaceLayout } from "@/components/shell/WorkspaceLayout";
import { NetworkCanvas } from "@/features/network/NetworkCanvas";
import type { RouteOverlay } from "@/features/network/toFlow";
import { useRun, useRunResult, useVersion } from "@/lib/api/hooks";
import type { RunResultOut } from "@/lib/api/types";
import { useWorkspace } from "@/stores/workspace";
import { Inspector } from "./Inspector";
import { RunLauncher } from "./RunLauncher";
import { RunMonitor } from "./RunMonitor";
import { ScenarioPanel } from "./ScenarioPanel";

/** Route overlay = exactly the edge ids the shared evaluator stored for each vehicle. */
export function routesFromResult(result: RunResultOut | undefined): RouteOverlay[] {
  return (
    result?.evaluation?.routes.map((r) => ({
      vehicleId: r.vehicle_id,
      edgeIds: r.legs.flatMap((l) => l.edge_ids),
    })) ?? []
  );
}

export function CommandCenter() {
  const versionId = useWorkspace((s) => s.versionId);
  const activeRunId = useWorkspace((s) => s.activeRunId);
  const version = useVersion(versionId);
  const run = useRun(activeRunId);
  // Only overlay a result that belongs to the loaded scenario version.
  const runForVersion = run.data?.scenario_version_id === versionId ? run.data : undefined;
  const result = useRunResult(runForVersion);
  const routes = useMemo(() => routesFromResult(result.data), [result.data]);
  const compareRunId = useWorkspace((s) => s.compareRunId);
  const compareRun = useRun(compareRunId);
  const compareForVersion =
    compareRun.data?.scenario_version_id === versionId ? compareRun.data : undefined;
  const compareResult = useRunResult(compareForVersion);
  const altRoutes = useMemo(() => routesFromResult(compareResult.data), [compareResult.data]);

  let center: React.ReactNode;
  if (!versionId) {
    center = (
      <div className="grid h-full place-items-center">
        <EmptyState>Load a saved scenario or import a built-in one to begin.</EmptyState>
      </div>
    );
  } else if (version.isPending) {
    center = (
      <div className="grid h-full place-items-center">
        <LoadingState label="Loading network…" />
      </div>
    );
  } else if (version.isError) {
    center = (
      <div className="grid h-full place-items-center p-6">
        <ErrorState error={version.error} title="Could not load the scenario version" />
      </div>
    );
  } else {
    center = <NetworkCanvas scenario={version.data.data} routes={routes} altRoutes={altRoutes} />;
  }

  return (
    <WorkspaceLayout
      left={
        <>
          <ScenarioPanel />
          <RunLauncher />
        </>
      }
      center={center}
      right={
        version.data ? (
          <Inspector
            scenario={version.data.data}
            run={runForVersion}
            result={result.data}
            resultLoading={result.isLoading}
            resultError={result.error}
            compareRun={compareForVersion}
            compareResult={compareResult.data}
          />
        ) : (
          <div className="p-3">
            <EmptyState>Nothing to inspect yet.</EmptyState>
          </div>
        )
      }
      bottom={<RunMonitor />}
    />
  );
}
