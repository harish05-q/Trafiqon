// Pure builder for convergence charts (tested without a canvas). Series colours come from the
// experiment series tokens, never from traffic colours.

export interface Point {
  x: number;
  y: number;
}

export interface ConvergenceSeries {
  name: string;
  points: Point[];
  /** "stored" = run_results.history; "live" = progress events received so far. */
  source: "stored" | "live";
}

export type XAxis = "iteration" | "elapsed_s";

export const X_LABEL: Record<XAxis, string> = {
  iteration: "Iteration (algorithm-specific unit)",
  elapsed_s: "Elapsed wall time (s, measured)",
};

interface HistoryLike {
  iteration: number;
  elapsed_s: number;
  best_objective: number | null;
}

/** Best-so-far points; samples before the first feasible solution are omitted, not zeroed. */
export function historyToPoints(history: HistoryLike[], axis: XAxis): Point[] {
  return history
    .filter((h) => h.best_objective !== null && Number.isFinite(h.best_objective))
    .map((h) => ({ x: axis === "iteration" ? h.iteration : h.elapsed_s, y: h.best_objective! }));
}

export function buildConvergenceOption(
  series: ConvergenceSeries[],
  axis: XAxis,
  colors: { series: string[]; text: string; muted: string; grid: string },
) {
  return {
    animation: false, // the chart reflects data as received; no decorative motion
    color: colors.series,
    textStyle: { color: colors.text, fontFamily: "var(--font-inter), sans-serif" },
    grid: { left: 64, right: 16, top: 32, bottom: 44 },
    legend: {
      top: 4,
      textStyle: { color: colors.text, fontSize: 11 },
      data: series.map((s) => s.name),
    },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => `${v.toFixed(3)} min` },
    xAxis: {
      type: "value",
      name: X_LABEL[axis],
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: colors.muted, fontSize: 11 },
      axisLabel: { color: colors.muted, fontSize: 10 },
      splitLine: { lineStyle: { color: colors.grid } },
    },
    yAxis: {
      type: "value",
      scale: true,
      name: "Best feasible objective (min)",
      nameLocation: "middle",
      nameGap: 48,
      nameTextStyle: { color: colors.muted, fontSize: 11 },
      axisLabel: { color: colors.muted, fontSize: 10 },
      splitLine: { lineStyle: { color: colors.grid } },
    },
    series: series.map((s) => ({
      name: s.name,
      type: "line",
      step: "end", // best-so-far only changes at improvements
      showSymbol: s.points.length < 40,
      symbolSize: 4,
      lineStyle: { width: 1.5, type: s.source === "live" ? "dashed" : "solid" },
      data: s.points.map((p) => [p.x, p.y]),
    })),
  };
}
