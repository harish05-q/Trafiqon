"use client";

import { useEffect, useRef } from "react";

import { EmptyState } from "@/components/status";
import { buildConvergenceOption, type ConvergenceSeries, type XAxis } from "./convergence";
import { buildSeedScatterOption, type SeedRun } from "./seeds";

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

type Colors = { series: string[]; text: string; muted: string; grid: string };

/** Chart kinds: serializable input + a module-level option builder (no closures in deps). */
const BUILDERS = {
  convergence: (i: { series: ConvergenceSeries[]; axis: XAxis }, c: Colors) =>
    buildConvergenceOption(i.series, i.axis, c),
  seeds: (i: { runs: SeedRun[]; specs: string[] }, c: Colors) =>
    buildSeedScatterOption(i.runs, i.specs, c),
};

/** ECharts wrapper. Re-renders only when the serialized input or the theme changes, and
 * re-reads colour tokens so charts follow the workspace theme. */
function EChart<K extends keyof typeof BUILDERS>({
  kind,
  input,
  height,
  label,
}: {
  kind: K;
  input: Parameters<(typeof BUILDERS)[K]>[0];
  height: number;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = typeof document === "undefined" ? "dark" : document.documentElement.dataset.theme;
  const spec = JSON.stringify({ kind, input, theme });

  useEffect(() => {
    if (!ref.current) return;
    const { kind, input } = JSON.parse(spec) as { kind: K; input: never };
    let disposed = false;
    let chart: import("echarts").ECharts | undefined;
    let observer: ResizeObserver | undefined;
    import("echarts").then((echarts) => {
      if (disposed || !ref.current) return;
      chart = echarts.init(ref.current, undefined, { renderer: "svg" });
      const colors: Colors = {
        series: [1, 2, 3, 4].map((i) => token(`--tq-series-${i}`)),
        text: token("--tq-text"),
        muted: token("--tq-text-secondary"),
        grid: token("--tq-border"),
      };
      chart.setOption(BUILDERS[kind](input, colors) as never, true);
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(ref.current);
    });
    return () => {
      disposed = true;
      observer?.disconnect();
      chart?.dispose();
    };
  }, [spec]);

  return <div ref={ref} role="img" aria-label={label} style={{ height, width: "100%" }} />;
}

/** Best-so-far objective over iterations or wall time. */
export function ConvergenceChart({
  series,
  axis,
  height = 240,
  label,
}: {
  series: ConvergenceSeries[];
  axis: XAxis;
  height?: number;
  label: string;
}) {
  if (!series.some((s) => s.points.length > 0)) {
    return <EmptyState>No feasible objective values to plot yet.</EmptyState>;
  }
  return <EChart kind="convergence" input={{ series, axis }} height={height} label={label} />;
}

/** Objective of every completed feasible run, one column per spec, with the spec mean. */
export function SeedChart({
  runs,
  specs,
  height = 260,
  label,
}: {
  runs: SeedRun[];
  specs: string[];
  height?: number;
  label: string;
}) {
  if (!runs.some((r) => r.feasible && r.objective !== null)) {
    return <EmptyState>No completed feasible runs to plot yet.</EmptyState>;
  }
  return <EChart kind="seeds" input={{ runs, specs }} height={height} label={label} />;
}
