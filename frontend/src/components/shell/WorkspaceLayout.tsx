"use client";

import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/stores/workspace";

/**
 * Left controls · central network · right inspector · bottom panel. Side and bottom panels
 * collapse; below the lg breakpoint they stack under the network so it is never covered.
 */
export function WorkspaceLayout({
  left,
  center,
  right,
  bottom,
}: {
  left: React.ReactNode;
  center: React.ReactNode;
  right: React.ReactNode;
  bottom: React.ReactNode;
}) {
  const panels = useWorkspace((s) => s.panels);
  const toggle = useWorkspace((s) => s.togglePanel);
  return (
    <div className="flex h-full flex-col overflow-y-auto lg:overflow-hidden">
      <div className="flex min-h-0 flex-col lg:flex-1 lg:flex-row">
        <aside
          aria-label="Controls"
          className={cn(
            "bg-card order-2 border-t lg:order-1 lg:border-t-0 lg:border-r",
            panels.left ? "lg:w-80" : "lg:w-9",
            "flex shrink-0 flex-col",
          )}
        >
          <PanelToggle
            label="controls"
            open={panels.left}
            onClick={() => toggle("left")}
            icon={panels.left ? <ChevronLeft /> : <ChevronRight />}
          />
          {panels.left && <div className="min-h-0 flex-1 overflow-y-auto">{left}</div>}
        </aside>
        <main className="relative order-1 h-[60vh] min-w-0 flex-1 lg:order-2 lg:h-auto">
          {center}
        </main>
        <aside
          aria-label="Inspector"
          className={cn(
            "bg-card order-3 flex shrink-0 flex-col border-t lg:border-t-0 lg:border-l",
            panels.right ? "lg:w-80" : "lg:w-9",
          )}
        >
          <PanelToggle
            label="inspector"
            open={panels.right}
            onClick={() => toggle("right")}
            icon={panels.right ? <ChevronRight /> : <ChevronLeft />}
          />
          {panels.right && <div className="min-h-0 flex-1 overflow-y-auto">{right}</div>}
        </aside>
      </div>
      <section
        aria-label="Run details"
        className={cn("bg-card shrink-0 border-t", panels.bottom ? "lg:h-60" : "")}
      >
        <PanelToggle
          label="run details"
          open={panels.bottom}
          onClick={() => toggle("bottom")}
          icon={panels.bottom ? <ChevronDown /> : <ChevronUp />}
          horizontal
        />
        {panels.bottom && <div className="h-[calc(100%-1.75rem)] overflow-y-auto">{bottom}</div>}
      </section>
    </div>
  );
}

function PanelToggle({
  label,
  open,
  onClick,
  icon,
  horizontal,
}: {
  label: string;
  open: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  horizontal?: boolean;
}) {
  return (
    <div className={cn("hidden justify-end px-1 pt-1 lg:flex", horizontal && "h-7")}>
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={onClick}
        aria-expanded={open}
        aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
      >
        {icon}
      </Button>
    </div>
  );
}
