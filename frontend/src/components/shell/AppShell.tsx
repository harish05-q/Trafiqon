"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { formatSimTime } from "@/features/simulation/simView";
import { useHealth, useSimulation, useVersion } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { ActiveRunStream } from "@/lib/api/events";
import { useWorkspace, workspaceFromPath } from "@/stores/workspace";

export const WORKSPACES = [
  { href: "/command-center", label: "Command Center" },
  { href: "/algorithm-lab", label: "Algorithm Lab" },
  { href: "/scenario-studio", label: "Scenario Studio" },
  { href: "/experiments", label: "Experiment Explorer" },
] as const;

/** Applies the current workspace's theme to <html data-theme> (colors flow from tokens). */
function ThemeSync({ theme }: { theme: string }) {
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return null;
}

function ServiceStatus() {
  const health = useHealth();
  let label = "API: checking";
  let tone = "text-muted-foreground";
  if (health.isError) {
    label = "API: unreachable";
    tone = "text-incident-text";
  } else if (health.data) {
    const db = health.data.dependencies.database?.status;
    label = db === "ok" ? "API: online · DB: ok" : `API: online · DB: ${db}`;
    tone = db === "ok" ? "text-traffic-normal" : "text-traffic-congested";
  }
  return (
    <span className={cn("flex items-center gap-1.5 text-xs", tone)} role="status">
      <span aria-hidden="true" className="inline-block size-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

function SimulationStatus() {
  const simulationId = useWorkspace((s) => s.simulationId);
  const sim = useSimulation(simulationId);
  if (!simulationId || !sim.data) {
    return <span className="text-muted-foreground hidden text-xs md:inline">Simulation: none</span>;
  }
  return (
    <span className="hidden text-xs md:inline" role="status">
      Simulation: {sim.data.status}{" "}
      <span className="num text-muted-foreground">
        {formatSimTime(sim.data.time_min)} · {sim.data.served_count}/{sim.data.customer_count}{" "}
        served
      </span>
    </span>
  );
}

function CurrentScenario() {
  const versionId = useWorkspace((s) => s.versionId);
  const version = useVersion(versionId);
  if (!versionId) return <span className="text-muted-foreground text-xs">No scenario loaded</span>;
  if (!version.data)
    return <span className="text-muted-foreground text-xs">Loading scenario…</span>;
  return (
    <span className="truncate text-xs" title={version.data.fingerprint}>
      {version.data.data.name}{" "}
      <span className="num text-muted-foreground">v{version.data.version_number}</span>
      {version.data.synthetic && <span className="text-muted-foreground"> · synthetic</span>}
    </span>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const workspace = workspaceFromPath(pathname);
  const theme = useWorkspace((s) => s.themes[workspace]);
  const toggleTheme = useWorkspace((s) => s.toggleTheme);
  return (
    <div className="flex h-dvh flex-col">
      <ThemeSync theme={theme} />
      <ActiveRunStream />
      <header className="bg-card flex h-11 shrink-0 items-center gap-4 border-b px-3">
        <span className="font-semibold tracking-wide">TRAFIQON</span>
        <nav aria-label="Workspaces" className="flex gap-0.5 overflow-x-auto">
          {WORKSPACES.map((w) => {
            const active = pathname?.startsWith(w.href);
            return (
              <Link
                key={w.href}
                href={w.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-sm px-2.5 py-1 text-xs whitespace-nowrap",
                  active
                    ? "bg-secondary text-foreground shadow-[inset_0_-2px_0_var(--tq-signal)]"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {w.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-4">
          <CurrentScenario />
          <SimulationStatus />
          <ServiceStatus />
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => toggleTheme(workspace)}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            title="Theme for this workspace"
          >
            {theme === "dark" ? <Sun /> : <Moon />}
          </Button>
        </div>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
