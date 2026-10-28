import { describe, expect, it } from "vitest";

import type { EdgeOut, ScenarioOut } from "@/lib/api/types";
import { CONGESTION_RATIO, SCALE, offsetSegment, toFlow, trafficState } from "./toFlow";

function edge(source: string, target: string, extra: Partial<EdgeOut> = {}): EdgeOut {
  return {
    id: `${source}->${target}`,
    source,
    target,
    distance: 1,
    base_time: 2,
    current_time: 2,
    closed: false,
    road_class: null,
    capacity: null,
    congestion: null,
    ...extra,
  };
}

const scenario: ScenarioOut = {
  id: "s",
  name: "S",
  description: "",
  synthetic: true,
  settings: {},
  graph: {
    nodes: [
      { id: "d", x: 0, y: 0, label: null },
      { id: "a", x: 1, y: 0, label: null },
      { id: "b", x: 2, y: 0, label: null },
    ],
    edges: [
      edge("d", "a"),
      edge("a", "d"),
      edge("a", "b", { current_time: 3 }),
      edge("b", "a", { closed: true }),
      edge("b", "d"),
    ],
  },
  depots: [{ id: "D1", node_id: "d" }],
  customers: [{ id: "C1", node_id: "b", demand: 4 }],
  vehicles: [],
};

describe("toFlow", () => {
  it("marks exactly the given route edges and their vehicles", () => {
    const { edges } = toFlow(scenario, {
      routes: [{ vehicleId: "v1", edgeIds: ["d->a", "a->b", "b->d"] }],
    });
    const onRoute = edges.filter((e) => e.data!.onRoute).map((e) => e.id);
    expect(onRoute.sort()).toEqual(["a->b", "b->d", "d->a"]);
    expect(edges.find((e) => e.id === "d->a")!.data!.vehicles).toEqual(["v1"]);
    expect(edges.find((e) => e.id === "a->d")!.data!.onRoute).toBe(false);
  });

  it("ignores unknown route edge ids instead of inventing roads", () => {
    const { edges } = toFlow(scenario, { routes: [{ vehicleId: "v1", edgeIds: ["nope"] }] });
    expect(edges.some((e) => e.data!.onRoute)).toBe(false);
    expect(edges).toHaveLength(5);
  });

  it("classifies traffic: closed beats congested; congested at the documented ratio", () => {
    expect(trafficState(edge("x", "y", { closed: true, current_time: 9 }))).toBe("closed");
    expect(trafficState(edge("x", "y", { current_time: 2 * CONGESTION_RATIO }))).toBe("congested");
    expect(trafficState(edge("x", "y", { current_time: 2 * CONGESTION_RATIO - 0.01 }))).toBe(
      "normal",
    );
    const { edges } = toFlow(scenario);
    expect(edges.find((e) => e.id === "a->b")!.data!.traffic).toBe("congested");
    expect(edges.find((e) => e.id === "b->a")!.data!.traffic).toBe("closed");
  });

  it("keeps direction and flags two-way pairs for offset drawing", () => {
    const { edges } = toFlow(scenario);
    const byId = Object.fromEntries(edges.map((e) => [e.id, e]));
    expect(byId["b->a"].source).toBe("b");
    expect(byId["d->a"].data!.hasReverse).toBe(true);
    expect(byId["b->d"].data!.hasReverse).toBe(false);
  });

  it("draws route edges above other roads", () => {
    const { edges } = toFlow(scenario, { routes: [{ vehicleId: "v1", edgeIds: ["d->a"] }] });
    expect(edges.at(-1)!.id).toBe("d->a");
  });

  it("dims other vehicles' routes when one route is selected", () => {
    const { edges } = toFlow(scenario, {
      routes: [
        { vehicleId: "v1", edgeIds: ["d->a"] },
        { vehicleId: "v2", edgeIds: ["b->d"] },
      ],
      selectedVehicleId: "v1",
    });
    expect(edges.find((e) => e.id === "d->a")!.data!.dimmed).toBe(false);
    expect(edges.find((e) => e.id === "b->d")!.data!.dimmed).toBe(true);
  });

  it("classifies nodes, scales coordinates and marks selection", () => {
    const { nodes } = toFlow(scenario, {
      routes: [{ vehicleId: "v1", edgeIds: ["d->a"] }],
      selectedNodeId: "b",
    });
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    expect(byId.d.data.kind).toBe("depot");
    expect(byId.b.data).toMatchObject({ kind: "customer", refId: "C1", demand: 4, selected: true });
    expect(byId.a.data.kind).toBe("intersection");
    expect(byId.b.position).toEqual({ x: 2 * SCALE, y: 0 });
    expect(byId.a.data.onRoute).toBe(true);
    expect(byId.b.data.onRoute).toBe(false);
  });
});

describe("offsetSegment", () => {
  it("shifts perpendicular to the direction of travel, opposite for the reverse edge", () => {
    const fwd = offsetSegment(0, 0, 10, 0, 3);
    const rev = offsetSegment(10, 0, 0, 0, 3);
    expect(fwd).toEqual({ x1: 0, y1: 3, x2: 10, y2: 3 });
    expect(rev.y1).toBe(-3);
    expect(offsetSegment(0, 0, 10, 0, 0)).toEqual({ x1: 0, y1: 0, x2: 10, y2: 0 });
  });
});
