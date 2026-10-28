"use client";

// Focused client-side workspace state (Zustand). Server data lives in TanStack Query.
// Persisted to localStorage so the selected scenario, active run and themes survive a refresh.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Theme = "dark" | "light";
export type WorkspaceKey = "command-center" | "algorithm-lab" | "scenario-studio" | "experiments";
export type Selection =
  | { kind: "node"; id: string }
  | { kind: "edge"; id: string }
  | { kind: "route"; vehicleId: string }
  | null;

/** Operational workspaces start dark (SPEC_FULL 13.3); experiment analysis starts on the warm
 * light theme. One theme per workspace, so surfaces are never mixed within a workspace. */
export const DEFAULT_THEMES: Record<WorkspaceKey, Theme> = {
  "command-center": "dark",
  "algorithm-lab": "dark",
  "scenario-studio": "dark",
  experiments: "light",
};

export function workspaceFromPath(pathname: string | null | undefined): WorkspaceKey {
  const seg = (pathname ?? "").split("/")[1];
  return (Object.keys(DEFAULT_THEMES) as WorkspaceKey[]).includes(seg as WorkspaceKey)
    ? (seg as WorkspaceKey)
    : "command-center";
}

export interface WorkspaceState {
  themes: Record<WorkspaceKey, Theme>;
  versionId: string | null;
  activeRunId: string | null;
  compareRunId: string | null;
  selection: Selection;
  panels: { left: boolean; right: boolean; bottom: boolean };
  toggleTheme: (workspace: WorkspaceKey) => void;
  setVersion: (versionId: string | null) => void;
  setActiveRun: (runId: string | null) => void;
  setCompareRun: (runId: string | null) => void;
  select: (selection: Selection) => void;
  togglePanel: (panel: keyof WorkspaceState["panels"]) => void;
}

const safeStorage = createJSONStorage(() => {
  try {
    const probe = "__trafiqon_probe__";
    window.localStorage.setItem(probe, probe);
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    const memory = new Map<string, string>();
    return {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => void memory.set(k, v),
      removeItem: (k: string) => void memory.delete(k),
    };
  }
});

export const useWorkspace = create<WorkspaceState>()(
  persist(
    (set) => ({
      themes: { ...DEFAULT_THEMES },
      versionId: null,
      activeRunId: null,
      compareRunId: null,
      selection: null,
      panels: { left: true, right: true, bottom: true },
      toggleTheme: (ws) =>
        set((s) => ({
          themes: { ...s.themes, [ws]: s.themes[ws] === "dark" ? "light" : "dark" },
        })),
      setVersion: (versionId) =>
        set((s) =>
          s.versionId === versionId
            ? s
            : { versionId, selection: null, activeRunId: null, compareRunId: null },
        ),
      setActiveRun: (activeRunId) =>
        set((s) => ({
          activeRunId,
          compareRunId: s.compareRunId === activeRunId ? null : s.compareRunId,
        })),
      setCompareRun: (compareRunId) => set({ compareRunId }),
      select: (selection) => set({ selection }),
      togglePanel: (panel) => set((s) => ({ panels: { ...s.panels, [panel]: !s.panels[panel] } })),
    }),
    {
      name: "trafiqon.workspace.v2",
      storage: safeStorage,
      partialize: (s) => ({
        themes: s.themes,
        versionId: s.versionId,
        activeRunId: s.activeRunId,
        compareRunId: s.compareRunId,
        panels: s.panels,
      }),
    },
  ),
);
