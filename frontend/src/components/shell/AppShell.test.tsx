import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_THEMES, useWorkspace, workspaceFromPath } from "@/stores/workspace";
import { installFetch } from "@/test/fake-api";
import { AppShell, WORKSPACES } from "./AppShell";

vi.mock("next/navigation", () => ({ usePathname: () => "/command-center" }));

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AppShell>
        <p>content</p>
      </AppShell>
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  beforeEach(() => useWorkspace.setState({ themes: { ...DEFAULT_THEMES }, versionId: null }));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    document.documentElement.removeAttribute("data-theme");
  });

  it("renders the four workspaces with the current one marked", () => {
    installFetch({
      "GET /api/v1/health": () => ({
        status: "ok",
        version: "0.1.0",
        api_version: "v1",
        dependencies: { database: { status: "ok" } },
      }),
    });
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Workspaces" });
    expect(nav.querySelectorAll("a")).toHaveLength(WORKSPACES.length);
    expect(screen.getByRole("link", { name: "Command Center" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(screen.getByText("content")).toBeTruthy();
  });

  it("shows real service status from /health, including degraded DB", async () => {
    installFetch({
      "GET /api/v1/health": () => ({
        status: "ok",
        version: "0.1.0",
        api_version: "v1",
        dependencies: { database: { status: "unavailable" } },
      }),
    });
    renderShell();
    expect(await screen.findByText("API: online · DB: unavailable")).toBeTruthy();
  });

  it("reports an unreachable API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("down");
      }),
    );
    renderShell();
    expect(await screen.findByText("API: unreachable")).toBeTruthy();
  });

  it("starts dark and switches theme through the token attribute", async () => {
    installFetch({});
    renderShell();
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
    expect(useWorkspace.getState().themes["command-center"]).toBe("light");
    expect(useWorkspace.getState().themes.experiments).toBe("light"); // untouched default
  });

  it("uses per-workspace themes: analysis starts light, operations start dark", () => {
    expect(DEFAULT_THEMES["command-center"]).toBe("dark");
    expect(DEFAULT_THEMES.experiments).toBe("light");
    expect(workspaceFromPath("/experiments")).toBe("experiments");
    expect(workspaceFromPath("/unknown")).toBe("command-center");
  });

  it("says simulation is not available rather than showing a fake state", () => {
    installFetch({});
    renderShell();
    expect(screen.getByText("Simulation: not available")).toBeTruthy();
  });
});
