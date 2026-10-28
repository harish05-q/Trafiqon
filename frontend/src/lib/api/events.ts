"use client";

// Server-Sent Events for run progress. ONE EventSource per active run is opened by
// <ActiveRunStream/> (mounted in the app shell); consumers read the shared log from a store.
// The browser's EventSource reconnects on its own and resends Last-Event-ID; the reducer
// dedupes any replayed events by id.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { create } from "zustand";

import { useWorkspace } from "@/stores/workspace";
import { api } from "./client";
import { keys } from "./hooks";
import type { RunEvent, RunProgress } from "./types";

export const LIFECYCLE_TYPES = [
  "queued",
  "started",
  "cancel_requested",
  "requeued",
  "completed",
  "cancelled",
  "failed",
] as const;
const STREAM_TYPES = [...LIFECYCLE_TYPES, "progress"] as const;
const MAX_KEPT = 200;

export interface EventLog {
  runId: string | null;
  events: RunEvent[]; // newest last, bounded
  lastId: number;
  latestProgress: RunProgress | null;
  ended: boolean;
  connection: "idle" | "open" | "reconnecting" | "closed";
}

export type EventAction =
  | { type: "reset"; runId: string | null }
  | { type: "event"; event: RunEvent }
  | { type: "connection"; state: EventLog["connection"] }
  | { type: "end" };

export const initialLog = (runId: string | null = null): EventLog => ({
  runId,
  events: [],
  lastId: 0,
  latestProgress: null,
  ended: false,
  connection: "idle",
});

/** Pure reducer: dedupes by event id (reconnects may replay), keeps order, bounds memory. */
export function eventReducer(state: EventLog, action: EventAction): EventLog {
  switch (action.type) {
    case "reset":
      return initialLog(action.runId);
    case "connection":
      return { ...state, connection: action.state };
    case "end":
      return { ...state, ended: true, connection: "closed" };
    case "event": {
      const e = action.event;
      if (e.id <= state.lastId) return state;
      const events = [...state.events, e].slice(-MAX_KEPT);
      return {
        ...state,
        events,
        lastId: e.id,
        latestProgress:
          e.kind === "progress" ? (e.payload as unknown as RunProgress) : state.latestProgress,
      };
    }
  }
}

interface EventLogStore {
  logs: Record<string, EventLog>;
  dispatch: (runId: string, action: EventAction) => void;
}

export const useEventLogs = create<EventLogStore>()((set) => ({
  logs: {},
  dispatch: (runId, action) =>
    set((s) => ({
      logs: { ...s.logs, [runId]: eventReducer(s.logs[runId] ?? initialLog(runId), action) },
    })),
}));

const EMPTY = initialLog();

export function useRunEventLog(runId: string | null): EventLog {
  return useEventLogs((s) => (runId ? (s.logs[runId] ?? EMPTY) : EMPTY));
}

/** Opens the SSE stream for `runId` and feeds the shared log. Mount once per run. */
export function useRunEventStream(runId: string | null): void {
  const qc = useQueryClient();
  const dispatch = useEventLogs((s) => s.dispatch);
  useEffect(() => {
    if (!runId || typeof EventSource === "undefined") return;
    dispatch(runId, { type: "reset", runId });
    const source = new EventSource(api.runEventsUrl(runId));
    source.onopen = () => dispatch(runId, { type: "connection", state: "open" });
    source.onerror = () =>
      dispatch(runId, {
        type: "connection",
        state: source.readyState === 2 ? "closed" : "reconnecting",
      });
    const onEvent = (msg: MessageEvent<string>) => {
      const event = JSON.parse(msg.data) as RunEvent;
      dispatch(runId, { type: "event", event });
      if (event.kind === "lifecycle") {
        qc.invalidateQueries({ queryKey: keys.run(runId) });
        qc.invalidateQueries({ queryKey: ["runs"] });
      }
    };
    for (const t of STREAM_TYPES) source.addEventListener(t, onEvent as EventListener);
    source.addEventListener("end", () => {
      dispatch(runId, { type: "end" });
      qc.invalidateQueries({ queryKey: keys.run(runId) });
      source.close();
    });
    return () => source.close();
  }, [runId, qc, dispatch]);
}

/** Streams events for the workspace's active run, wherever the user navigates. */
export function ActiveRunStream() {
  const activeRunId = useWorkspace((s) => s.activeRunId);
  useRunEventStream(activeRunId);
  return null;
}
