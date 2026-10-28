// Pure builder: objective of every completed, feasible run in a suite, one column per spec.
// Points are measured runs (no smoothing, no imputation); a dashed line marks each spec's mean.

export interface SeedRun {
  spec: string;
  seed: number | null;
  repetition: number;
  feasible: boolean;
  objective: number | null;
}

export function seedPoints(runs: SeedRun[], specs: string[]) {
  return specs.map((spec) =>
    runs
      .filter((r) => r.spec === spec && r.feasible && r.objective !== null)
      .map((r) => ({
        value: [spec, r.objective!] as [string, number],
        seed: r.seed,
        rep: r.repetition,
      })),
  );
}

export function buildSeedScatterOption(
  runs: SeedRun[],
  specs: string[],
  colors: { series: string[]; text: string; muted: string; grid: string },
) {
  const points = seedPoints(runs, specs);
  return {
    animation: false,
    color: colors.series,
    textStyle: { color: colors.text, fontFamily: "var(--font-inter), sans-serif" },
    grid: { left: 64, right: 16, top: 32, bottom: 40 },
    legend: { top: 4, textStyle: { color: colors.text, fontSize: 11 }, data: specs },
    tooltip: { trigger: "item" },
    xAxis: {
      type: "category",
      data: specs,
      name: "Algorithm spec",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: colors.muted, fontSize: 11 },
      axisLabel: { color: colors.muted, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      scale: true,
      name: "Objective (min, per seed)",
      nameLocation: "middle",
      nameGap: 48,
      nameTextStyle: { color: colors.muted, fontSize: 11 },
      axisLabel: { color: colors.muted, fontSize: 10 },
      splitLine: { lineStyle: { color: colors.grid } },
    },
    series: specs.map((spec, i) => ({
      name: spec,
      type: "scatter",
      symbolSize: 8,
      data: points[i].map((p) => ({
        value: p.value,
        name: `seed ${p.seed ?? "n/a"} · rep ${p.rep}`,
      })),
      markLine: points[i].length
        ? {
            symbol: "none",
            silent: true,
            lineStyle: { type: "dashed", width: 1 },
            label: { show: false },
            data: [
              {
                name: "mean",
                yAxis: points[i].reduce((a, p) => a + p.value[1], 0) / points[i].length,
              },
            ],
          }
        : undefined,
    })),
  };
}
