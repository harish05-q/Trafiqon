"use client";

import { Download } from "lucide-react";

import { EmptyState, ErrorState, LoadingState, Section } from "@/components/status";
import { Button } from "@/components/ui/button";
import {
  useBuiltinScenarios,
  useImportBuiltin,
  useSavedScenarios,
  useVersion,
} from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/stores/workspace";

export function ScenarioPanel() {
  const saved = useSavedScenarios();
  const builtin = useBuiltinScenarios();
  const importBuiltin = useImportBuiltin();
  const versionId = useWorkspace((s) => s.versionId);
  const setVersion = useWorkspace((s) => s.setVersion);
  const version = useVersion(versionId);

  return (
    <>
      <Section title="Saved scenarios">
        {saved.isPending && <LoadingState label="Loading scenarios…" />}
        {saved.isError && <ErrorState error={saved.error} />}
        {saved.data && saved.data.items.length === 0 && (
          <EmptyState>No saved scenarios yet. Import a built-in scenario below.</EmptyState>
        )}
        <ul className="grid gap-0.5">
          {saved.data?.items.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                disabled={!s.current_version_id}
                onClick={() => setVersion(s.current_version_id)}
                aria-pressed={s.current_version_id === versionId}
                className={cn(
                  "w-full rounded-sm px-2 py-1 text-left text-xs",
                  s.current_version_id === versionId
                    ? "bg-secondary shadow-[inset_2px_0_0_var(--tq-signal)]"
                    : "hover:bg-secondary/60",
                )}
              >
                {s.name}
              </button>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Built-in scenarios (synthetic)">
        {builtin.isError && <ErrorState error={builtin.error} />}
        {importBuiltin.isError && <ErrorState error={importBuiltin.error} title="Import failed" />}
        <ul className="grid gap-1">
          {builtin.data?.map((b) => (
            <li key={b.id} className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0">
                <span className="block truncate">{b.name}</span>
                <span className="num text-text-muted">
                  {b.node_count} nodes · {b.customer_count} customers · {b.vehicle_count} vehicles
                </span>
              </span>
              <Button
                size="xs"
                variant="outline"
                disabled={importBuiltin.isPending}
                onClick={() =>
                  importBuiltin.mutate(
                    { name: b.name, builtinId: b.id },
                    { onSuccess: (s) => setVersion(s.current_version_id) },
                  )
                }
                aria-label={`Import ${b.name} as a saved scenario`}
              >
                <Download aria-hidden="true" /> Import
              </Button>
            </li>
          ))}
        </ul>
      </Section>

      {version.data && (
        <Section title="Loaded version">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted-foreground">Version</dt>
            <dd className="num">v{version.data.version_number}</dd>
            <dt className="text-muted-foreground">Nodes / roads</dt>
            <dd className="num">
              {version.data.node_count} / {version.data.edge_count}
            </dd>
            <dt className="text-muted-foreground">Customers</dt>
            <dd className="num">{version.data.customer_count}</dd>
            <dt className="text-muted-foreground">Vehicles</dt>
            <dd className="num">{version.data.vehicle_count}</dd>
            <dt className="text-muted-foreground">Fingerprint</dt>
            <dd className="num truncate" title={version.data.fingerprint}>
              {version.data.fingerprint.slice(0, 12)}
            </dd>
          </dl>
        </Section>
      )}
    </>
  );
}
