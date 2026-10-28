import { describe, expect, it } from "vitest";

import { eventReducer, initialLog } from "./events";
import type { RunEvent } from "./types";

const ev = (id: number, kind: RunEvent["kind"], type: string, payload = {}): RunEvent => ({
  id,
  kind,
  type,
  payload,
  created_at: "2026-10-28T00:00:00Z",
});

describe("eventReducer", () => {
  it("appends in order and tracks the latest progress payload", () => {
    let s = initialLog("r1");
    s = eventReducer(s, { type: "event", event: ev(1, "lifecycle", "queued") });
    s = eventReducer(s, { type: "event", event: ev(2, "progress", "progress", { iteration: 5 }) });
    s = eventReducer(s, { type: "event", event: ev(3, "lifecycle", "completed") });
    expect(s.events.map((e) => e.id)).toEqual([1, 2, 3]);
    expect(s.latestProgress).toEqual({ iteration: 5 });
    expect(s.lastId).toBe(3);
  });

  it("drops replayed events after a reconnect (dedupe by id)", () => {
    let s = initialLog("r1");
    for (const id of [1, 2, 2, 1, 3]) {
      s = eventReducer(s, { type: "event", event: ev(id, "lifecycle", "x") });
    }
    expect(s.events.map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it("bounds memory", () => {
    let s = initialLog("r1");
    for (let id = 1; id <= 450; id++) {
      s = eventReducer(s, {
        type: "event",
        event: ev(id, "progress", "progress", { iteration: id }),
      });
    }
    expect(s.events).toHaveLength(200);
    expect(s.events[0].id).toBe(251);
    expect(s.latestProgress).toEqual({ iteration: 450 });
  });

  it("tracks connection state and end; reset clears everything", () => {
    let s = eventReducer(initialLog("r1"), { type: "connection", state: "open" });
    expect(s.connection).toBe("open");
    s = eventReducer(s, { type: "end" });
    expect(s).toMatchObject({ ended: true, connection: "closed" });
    expect(eventReducer(s, { type: "reset", runId: "r2" })).toEqual(initialLog("r2"));
  });
});
