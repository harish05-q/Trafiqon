import { describe, expect, it } from "vitest";

import type { ScenarioOut } from "@/lib/api/types";
import { SCALE, toFlow } from "./toFlow";

function edge(source: string, target: string, closed = false) {
  return {
    id: `${source}->${target}`,
    source,
    target,
    distance: 1,
    base_time: 2,
    current_time: 2,
    closed,
    road_class: null,
    capacity: null,
    congestion: null,
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
    edges: [edge("d", "a"), edge("a", "d"), edge("a", "b"), edge("b", "a", true)],
  },
  depots: [{ id: "D", node_id: "d" }],
  customers: [{ id: "B", node_id: "b", demand: 1 }],
  vehicles: [],
};

describe("toFlow", () => {
  it("marks exactly the API path edges as on-path", () => {
    const path = ["d->a", "a->b"];
    const { edges } = toFlow(scenario, path);
    const onPath = edges.filter((e) => e.data?.onPath).map((e) => e.id);
    expect(onPath.sort()).toEqual([...path].sort());
    expect(edges.find((e) => e.id === "a->d")?.data?.onPath).toBe(false);
  });

  it("draws on-path edges last and above parallel edges", () => {
    const { edges } = toFlow(scenario, ["a->b"]);
    expect(edges.at(-1)?.id).toBe("a->b");
    expect(edges.at(-1)?.zIndex).toBeGreaterThan(0);
  });

  it("keeps direction and marks closures", () => {
    const { edges } = toFlow(scenario);
    const closed = edges.find((e) => e.id === "b->a")!;
    expect(closed.source).toBe("b");
    expect(closed.target).toBe("a");
    expect(closed.data?.closed).toBe(true);
    expect(closed.className).toContain("closed");
  });

  it("classifies nodes and scales coordinates", () => {
    const { nodes } = toFlow(scenario, ["d->a"], ["d"]);
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    expect(byId.d.data.kind).toBe("depot");
    expect(byId.b.data.kind).toBe("customer");
    expect(byId.a.data.kind).toBe("intersection");
    expect(byId.b.position).toEqual({ x: 2 * SCALE, y: 0 });
    expect(byId.d.data.isEndpoint).toBe(true);
    expect(byId.a.data.onPath).toBe(true);
    expect(byId.b.data.onPath).toBe(false);
  });

  it("ignores unknown path ids instead of inventing edges", () => {
    const { edges } = toFlow(scenario, ["nope"]);
    expect(edges.some((e) => e.data?.onPath)).toBe(false);
    expect(edges).toHaveLength(4);
  });
});
