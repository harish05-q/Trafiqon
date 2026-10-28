import { describe, expect, it } from "vitest";

import { liveSeries } from "@/features/algorithm-lab/AlgorithmLab";
import type { RunEvent } from "@/lib/api/types";
import { buildConvergenceOption, historyToPoints, X_LABEL } from "./convergence";

const history = [
  { iteration: 0, elapsed_s: 0.0, best_objective: null },
  { iteration: 5, elapsed_s: 0.2, best_objective: 80 },
  { iteration: 10, elapsed_s: 0.5, best_objective: 75 },
];

describe("convergence", () => {
  it("omits points before the first feasible solution instead of plotting zero", () => {
    expect(historyToPoints(history, "iteration")).toEqual([
      { x: 5, y: 80 },
      { x: 10, y: 75 },
    ]);
    expect(historyToPoints(history, "elapsed_s").map((p) => p.x)).toEqual([0.2, 0.5]);
  });

  it("builds a labelled, non-animated step chart with series colours only", () => {
    const opt = buildConvergenceOption(
      [
        { name: "a", source: "stored", points: [{ x: 1, y: 2 }] },
        { name: "b", source: "live", points: [{ x: 1, y: 3 }] },
      ],
      "elapsed_s",
      { series: ["#s1", "#s2", "#s3", "#s4"], text: "#t", muted: "#m", grid: "#g" },
    );
    expect(opt.animation).toBe(false);
    expect(opt.color).toEqual(["#s1", "#s2", "#s3", "#s4"]);
    expect(opt.xAxis.name).toBe(X_LABEL.elapsed_s);
    expect(opt.yAxis.name).toMatch(/min/);
    expect(opt.series.map((s) => s.step)).toEqual(["end", "end"]);
    expect(opt.series.map((s) => s.lineStyle.type)).toEqual(["solid", "dashed"]);
    expect(opt.legend.data).toEqual(["a", "b"]);
  });

  it("live series uses only progress events with a feasible best", () => {
    const ev = (id: number, kind: RunEvent["kind"], payload: object): RunEvent => ({
      id,
      kind,
      type: kind === "progress" ? "progress" : "started",
      payload: payload as Record<string, unknown>,
      created_at: "",
    });
    const s = liveSeries(
      [
        ev(1, "lifecycle", {}),
        ev(2, "progress", { iteration: 1, elapsed_s: 0.1, best_objective: null }),
        ev(3, "progress", { iteration: 2, elapsed_s: 0.2, best_objective: 9 }),
      ],
      "iteration",
    );
    expect(s).toEqual({ name: "Live progress reports", source: "live", points: [{ x: 2, y: 9 }] });
  });
});
