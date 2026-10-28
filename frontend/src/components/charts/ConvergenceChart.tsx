"use client";

import { useEffect, useRef } from "react";

import { EmptyState } from "@/components/status";
import { buildConvergenceOption, type ConvergenceSeries, type XAxis } from "./convergence";

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** ECharts line chart of best-so-far objective. Re-reads tokens when the theme changes. */
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
  const ref = useRef<HTMLDivElement>(null);
  const hasData = series.some((s) => s.points.length > 0);
  const theme = typeof document === "undefined" ? "dark" : document.documentElement.dataset.theme;
  // Serialized input: re-render the chart only when the plotted data actually changes.
  const spec = JSON.stringify({ series, axis, theme });

  useEffect(() => {
    if (!ref.current || !hasData) return;
    const { series, axis } = JSON.parse(spec) as { series: ConvergenceSeries[]; axis: XAxis };
    let disposed = false;
    let chart: import("echarts").ECharts | undefined;
    let observer: ResizeObserver | undefined;
    import("echarts").then((echarts) => {
      if (disposed || !ref.current) return;
      chart = echarts.init(ref.current, undefined, { renderer: "svg" });
      chart.setOption(
        buildConvergenceOption(series, axis, {
          series: [1, 2, 3, 4].map((i) => token(`--tq-series-${i}`)),
          text: token("--tq-text"),
          muted: token("--tq-text-secondary"),
          grid: token("--tq-border"),
        }) as never,
        true,
      );
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(ref.current);
    });
    return () => {
      disposed = true;
      observer?.disconnect();
      chart?.dispose();
    };
  }, [spec, hasData]);

  if (!hasData) {
    return <EmptyState>No feasible objective values to plot yet.</EmptyState>;
  }
  return <div ref={ref} role="img" aria-label={label} style={{ height, width: "100%" }} />;
}
