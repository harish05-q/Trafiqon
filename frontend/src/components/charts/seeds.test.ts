import { describe, expect, it } from "vitest";

import { buildSeedScatterOption, seedPoints } from "./seeds";

const runs = [
  { spec: "sa", seed: 0, repetition: 0, feasible: true, objective: 70 },
  { spec: "sa", seed: 1, repetition: 1, feasible: true, objective: 74 },
  { spec: "sa", seed: 2, repetition: 2, feasible: false, objective: null },
  { spec: "qpso", seed: 0, repetition: 0, feasible: true, objective: 71 },
];

describe("seed chart", () => {
  it("plots only feasible runs with an objective, per spec, without imputing", () => {
    const pts = seedPoints(runs, ["sa", "qpso", "ortools"]);
    expect(pts.map((p) => p.length)).toEqual([2, 1, 0]);
    expect(pts[0][1]).toEqual({ value: ["sa", 74], seed: 1, rep: 1 });
  });

  it("marks each spec's mean and uses the series palette", () => {
    const opt = buildSeedScatterOption(runs, ["sa", "qpso", "ortools"], {
      series: ["#1", "#2", "#3", "#4"],
      text: "#t",
      muted: "#m",
      grid: "#g",
    });
    expect(opt.color).toEqual(["#1", "#2", "#3", "#4"]);
    expect(opt.series[0].markLine!.data[0].yAxis).toBe(72);
    expect(opt.series[2].markLine).toBeUndefined();
    expect(opt.yAxis.name).toMatch(/min/);
    expect(opt.animation).toBe(false);
  });
});
