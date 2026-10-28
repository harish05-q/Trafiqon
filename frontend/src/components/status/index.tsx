import { AlertTriangle, Ban, CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import type { RunStatus } from "@/lib/api/types";

/** A titled section inside a side or bottom panel. */
export function Section({
  title,
  actions,
  children,
  className,
}: {
  title: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-b px-3 py-3 last:border-b-0", className)} aria-label={title}>
      <header className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold">{title}</h2>
        {actions}
      </header>
      {children}
    </section>
  );
}

const STATUS: Record<RunStatus, { icon: React.ElementType; tone: string; spin?: boolean }> = {
  QUEUED: { icon: CircleDashed, tone: "text-muted-foreground" },
  RUNNING: { icon: Loader2, tone: "text-signal-text", spin: true },
  CANCELLING: { icon: Loader2, tone: "text-traffic-congested", spin: true },
  CANCELLED: { icon: Ban, tone: "text-muted-foreground" },
  COMPLETED: { icon: CheckCircle2, tone: "text-traffic-normal" },
  FAILED: { icon: XCircle, tone: "text-incident-text" },
};

/** Run status with icon + text label (never color alone). */
export function RunStatusBadge({ status }: { status: RunStatus }) {
  const s = STATUS[status];
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", s.tone)}>
      <Icon aria-hidden="true" className={cn("size-3.5", s.spin && "motion-safe:animate-spin")} />
      {status}
    </span>
  );
}

export type QuantityKind = "measured" | "derived";

/** A labelled numeric readout. `kind` marks measured vs derived quantities. */
export function Stat({
  label,
  value,
  unit,
  kind,
  digits = 2,
}: {
  label: string;
  value: number | string | null | undefined;
  unit?: string;
  kind?: QuantityKind;
  digits?: number;
}) {
  const shown =
    value === null || value === undefined
      ? "–"
      : typeof value === "number"
        ? value.toFixed(digits)
        : value;
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground flex items-center gap-1 text-xs">
        {label}
        {kind && (
          <span className="text-muted-foreground text-[10px]" title={`${kind} quantity`}>
            {kind === "measured" ? "meas." : "deriv."}
          </span>
        )}
      </dt>
      <dd className="num truncate text-sm">
        {shown}
        {unit && shown !== "–" && (
          <span className="text-muted-foreground ml-1 text-xs">{unit}</span>
        )}
      </dd>
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="text-muted-foreground text-xs">{children}</p>;
}

export function LoadingState({ label }: { label: string }) {
  return (
    <p className="text-muted-foreground flex items-center gap-2 text-xs" role="status">
      <Loader2 aria-hidden="true" className="size-3.5 motion-safe:animate-spin" />
      {label}
    </p>
  );
}

export function ErrorState({ error, title = "Request failed" }: { error: Error; title?: string }) {
  return (
    <div
      role="alert"
      className="border-incident/60 text-incident-text rounded-sm border px-2 py-1.5 text-xs"
    >
      <p className="flex items-center gap-1 font-medium">
        <AlertTriangle aria-hidden="true" className="size-3.5" />
        {title}
      </p>
      <p className="text-foreground mt-0.5">{error.message}</p>
    </div>
  );
}
