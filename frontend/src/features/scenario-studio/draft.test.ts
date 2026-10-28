import { describe, expect, it } from "vitest";

import {
  draftReducer,
  emptyScenario,
  initialDraft,
  NEW_ROAD_KMH,
  type Draft,
  type DraftAction,
} from "./draft";

function run(actions: DraftAction[], start: Draft = initialDraft()): Draft {
  return actions.reduce(draftReducer, start);
}

const twoNodes = (): Draft =>
  run([
    { type: "addNode", x: 0, y: 0 },
    { type: "addNode", x: 3, y: 4 },
  ]);

describe("draftReducer", () => {
  it("adds nodes with unique ids and marks the draft dirty", () => {
    const d = twoNodes();
    expect(d.data.graph.nodes.map((n) => n.id)).toEqual(["n1", "n2"]);
    expect(d.dirty).toBe(true);
    const after = run(
      [
        { type: "deleteNode", id: "n1" },
        { type: "addNode", x: 1, y: 1 },
      ],
      d,
    );
    expect(after.data.graph.nodes.map((n) => n.id)).toEqual(["n2", "n1"]); // reuses the free id
  });

  it("adds directed roads with geometry-based defaults and unique ids for parallel roads", () => {
    const d = run([{ type: "addEdge", source: "n1", target: "n2" }], twoNodes());
    const e = d.data.graph.edges[0];
    expect(e).toMatchObject({
      id: "n1->n2",
      source: "n1",
      target: "n2",
      distance: 5,
      closed: false,
    });
    expect(e.base_time).toBeCloseTo((5 / NEW_ROAD_KMH) * 60);
    expect(e.current_time).toBe(e.base_time);
    const parallel = run([{ type: "addEdge", source: "n1", target: "n2" }], d);
    expect(parallel.data.graph.edges.map((x) => x.id)).toEqual(["n1->n2", "n1->n2#2"]);
  });

  it("rejects self-loops and unknown endpoints without changing the draft", () => {
    const d = twoNodes();
    for (const a of [
      { type: "addEdge", source: "n1", target: "n1" },
      { type: "addEdge", source: "n1", target: "zz" },
    ] as DraftAction[]) {
      const r = draftReducer(d, a);
      expect(r.error).toBeTruthy();
      expect(r.data).toBe(d.data);
    }
  });

  it("validates road edits and derives the congestion factor", () => {
    const d = run([{ type: "addEdge", source: "n1", target: "n2" }], twoNodes());
    const bad = draftReducer(d, { type: "updateEdge", id: "n1->n2", patch: { current_time: -1 } });
    expect(bad.error).toMatch(/current_time/);
    const nan = draftReducer(d, { type: "updateEdge", id: "n1->n2", patch: { distance: NaN } });
    expect(nan.error).toMatch(/distance/);
    const ok = run(
      [
        { type: "updateEdge", id: "n1->n2", patch: { base_time: 10, current_time: 15 } },
        { type: "updateEdge", id: "n1->n2", patch: { closed: true } },
      ],
      d,
    );
    expect(ok.data.graph.edges[0]).toMatchObject({
      base_time: 10,
      current_time: 15,
      congestion: 1.5,
      closed: true,
    });
  });

  it("deleting a node removes its roads and its customer", () => {
    const d = run(
      [
        { type: "addEdge", source: "n1", target: "n2" },
        { type: "addEdge", source: "n2", target: "n1" },
        { type: "setRole", nodeId: "n2", role: "customer" },
        { type: "deleteNode", id: "n2" },
      ],
      twoNodes(),
    );
    expect(d.data.graph.edges).toEqual([]);
    expect(d.data.customers).toEqual([]);
  });

  it("roles: depot and customer ids, demand validation", () => {
    const d = run(
      [
        { type: "setRole", nodeId: "n1", role: "depot" },
        { type: "setRole", nodeId: "n2", role: "customer" },
      ],
      twoNodes(),
    );
    expect(d.data.depots).toEqual([{ id: "d1", node_id: "n1" }]);
    expect(d.data.customers).toEqual([{ id: "c1", node_id: "n2", demand: 1 }]);
    expect(
      draftReducer(d, { type: "setDemand", customerId: "c1", demand: 2.5 }).error,
    ).toBeTruthy();
    expect(draftReducer(d, { type: "setDemand", customerId: "c1", demand: 0 }).error).toBeTruthy();
    expect(
      draftReducer(d, { type: "setDemand", customerId: "c1", demand: 7 }).data.customers[0].demand,
    ).toBe(7);
    const swapped = draftReducer(d, { type: "setRole", nodeId: "n2", role: "depot" });
    expect(swapped.data.customers).toEqual([]);
    expect(swapped.data.depots.map((x) => x.id)).toEqual(["d1", "d2"]);
  });

  it("protects depots that vehicles use", () => {
    const d = run(
      [{ type: "setRole", nodeId: "n1", role: "depot" }, { type: "addVehicle" }],
      twoNodes(),
    );
    expect(d.data.vehicles).toEqual([
      { id: "v1", capacity: 10, start_depot_id: "d1", end_depot_ids: [] },
    ]);
    expect(draftReducer(d, { type: "deleteNode", id: "n1" }).error).toMatch(/v1/);
    expect(draftReducer(d, { type: "setRole", nodeId: "n1", role: "intersection" }).error).toMatch(
      /v1/,
    );
    const freed = run(
      [
        { type: "deleteVehicle", id: "v1" },
        { type: "deleteNode", id: "n1" },
      ],
      d,
    );
    expect(freed.error).toBeNull();
    expect(freed.data.depots).toEqual([]);
  });

  it("vehicles need a depot and integer capacity", () => {
    expect(draftReducer(twoNodes(), { type: "addVehicle" }).error).toMatch(/depot/);
    const d = run(
      [{ type: "setRole", nodeId: "n1", role: "depot" }, { type: "addVehicle" }],
      twoNodes(),
    );
    expect(draftReducer(d, { type: "updateVehicle", id: "v1", capacity: 0 }).error).toBeTruthy();
    expect(
      draftReducer(d, { type: "updateVehicle", id: "v1", startDepotId: "nope" }).error,
    ).toBeTruthy();
    expect(
      draftReducer(d, { type: "updateVehicle", id: "v1", capacity: 12 }).data.vehicles[0].capacity,
    ).toBe(12);
  });

  it("load resets dirty state; markSaved clears it", () => {
    const d = twoNodes();
    expect(draftReducer(d, { type: "markSaved" }).dirty).toBe(false);
    const loaded = draftReducer(d, { type: "load", data: emptyScenario() });
    expect(loaded).toEqual(initialDraft(emptyScenario()));
  });
});
