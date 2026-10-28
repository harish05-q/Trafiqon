"use client";

// Focused client-side workspace state (Zustand). Server data lives in TanStack Query.
// Persisted to localStorage so the selected scenario, active run and theme survive a refresh.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Theme = "dark" | "light";
export type Selection =
  | { kind: "node"; id: string }
  | { kind: "edge"; id: string }
  | { kind: "route"; vehicleId: string }
  | null;

export interface WorkspaceState {
  theme: Theme;
  versionId: string | null;
  activeRunId: string | null;
  selection: Selection;
  panels: { left: boolean; right: boolean; bottom: boolean };
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  setVersion: (versionId: string | null) => void;
  setActiveRun: (runId: string | null) => void;
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
      theme: "dark", // the command center always starts dark (SPEC_FULL 13.3)
      versionId: null,
      activeRunId: null,
      selection: null,
      panels: { left: true, right: true, bottom: true },
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
      setVersion: (versionId) =>
        set((s) =>
          s.versionId === versionId ? s : { versionId, selection: null, activeRunId: null },
        ),
      setActiveRun: (activeRunId) => set({ activeRunId }),
      select: (selection) => set({ selection }),
      togglePanel: (panel) => set((s) => ({ panels: { ...s.panels, [panel]: !s.panels[panel] } })),
    }),
    {
      name: "trafiqon.workspace.v1",
      storage: safeStorage,
      partialize: (s) => ({
        theme: s.theme,
        versionId: s.versionId,
        activeRunId: s.activeRunId,
        panels: s.panels,
      }),
    },
  ),
);
