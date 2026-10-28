import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RouteOverlay } from "@/features/network/toFlow";
import { ActiveRunStream } from "@/lib/api/events";
import { useWorkspace } from "@/stores/workspace";
import {
  FakeEventSource,
  algorithms,
  installFetch,
  makeRun,
  result,
  savedScenario,
  version,
} from "@/test/fake-api";
import { CommandCenter, routesFromResult } from "./CommandCenter";

// React Flow needs real layout; here we check what the workspace hands to the renderer.
const canvasProps: { routes?: RouteOverlay[] }[] = [];
vi.mock("@/features/network/NetworkCanvas", () => ({
  NetworkCanvas: (props: { routes?: RouteOverlay[] }) => {
    canvasProps.push(props);
    return <div data-testid="network" />;
  },
}));

function renderCC() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ActiveRunStream />
      <CommandCenter />
    </QueryClientProvider>,
  );
}

const baseRoutes = {
  "GET /api/v1/scenarios": () => ({ items: [savedScenario], total: 1, limit: 50, offset: 0 }),
  "GET /api/v1/scenarios/builtin": () => [
    {
      id: "urban_grid",
      name: "Urban Grid",
      description: "",
      synthetic: true,
      node_count: 30,
      edge_count: 80,
      customer_count: 10,
      vehicle_count: 3,
    },
  ],
  "GET /api/v1/algorithms": () => algorithms,
  "GET /api/v1/scenario-versions/ver-1": () => version,
  "GET /api/v1/runs": () => ({ items: [], total: 0, limit: 20, offset: 0 }),
};

describe("Command Center", () => {
  beforeEach(() => {
    canvasProps.length = 0;
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    useWorkspace.setState({
      versionId: null,
      activeRunId: null,
      compareRunId: null,
      selection: null,
    });
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows an empty state, then loads a saved scenario's version into the canvas", async () => {
    installFetch(baseRoutes);
    renderCC();
    expect(screen.getByText(/Load a saved scenario/)).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Urban Grid" }));
    await screen.findByTestId("network");
    expect(useWorkspace.getState().versionId).toBe("ver-1");
    expect(screen.getByText("abcdef012345")).toBeTruthy(); // fingerprint prefix
  });

  it("imports a built-in scenario through the API", async () => {
    const { calls } = installFetch({
      ...baseRoutes,
      "POST /api/v1/scenarios": () => ({ ...savedScenario, versions: [] }),
    });
    renderCC();
    fireEvent.click(await screen.findByRole("button", { name: /Import Urban Grid/ }));
    await waitFor(() => expect(useWorkspace.getState().versionId).toBe("ver-1"));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      name: "Urban Grid",
      builtin_id: "urban_grid",
    });
  });

  it("submits a run with the shown budget and follows it over SSE to a drawn result", async () => {
    useWorkspace.setState({ versionId: "ver-1" });
    let run = makeRun();
    const { calls } = installFetch({
      ...baseRoutes,
      "POST /api/v1/runs": () => run,
      "GET /api/v1/runs/run-1": () => run,
      "GET /api/v1/runs/run-1/result": () => result,
    });
    renderCC();
    const seed = await screen.findByLabelText(/Seed/);
    fireEvent.change(seed, { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText(/Iterations/), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Launch run" }));

    await waitFor(() => expect(useWorkspace.getState().activeRunId).toBe("run-1"));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      scenario_version_id: "ver-1",
      algorithm_id: "qpso_hybrid",
      config: { iterations: 30, swarm_size: 20 },
      seed: 42,
    });

    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const es = FakeEventSource.instances[0];
    expect(es.url).toMatch(/\/api\/v1\/runs\/run-1\/events$/);
    run = makeRun({ status: "RUNNING", started_at: "2026-10-28T00:00:01Z", attempt: 1 });
    act(() => {
      es.emit("started", {
        id: 2,
        kind: "lifecycle",
        type: "started",
        payload: { attempt: 1 },
        created_at: "2026-10-28T00:00:01Z",
      });
      es.emit("progress", {
        id: 3,
        kind: "progress",
        type: "progress",
        created_at: "2026-10-28T00:00:02Z",
        payload: {
          iteration: 7,
          evaluations: 1234,
          elapsed_s: 0.4,
          best_objective: 4.5,
          current_objective: 5,
          has_feasible: true,
          message: "",
          attempt: 1,
        },
      });
    });
    const monitor = screen.getByRole("region", { name: "Active run" });
    await within(monitor).findByText("RUNNING");
    expect(within(monitor).getByText("1234")).toBeTruthy();
    expect(within(monitor).getByText("4.500")).toBeTruthy();

    run = makeRun({
      status: "COMPLETED",
      started_at: "2026-10-28T00:00:01Z",
      attempt: 1,
      finished_at: "2026-10-28T00:00:03Z",
    });
    act(() => {
      es.emit("completed", {
        id: 4,
        kind: "lifecycle",
        type: "completed",
        payload: { feasible: true, objective: 4 },
        created_at: "2026-10-28T00:00:03Z",
      });
      es.emit("end", { status: "COMPLETED" });
    });
    await screen.findByRole("list", { name: "Vehicle routes" });
    expect(canvasProps.at(-1)!.routes).toEqual([
      { vehicleId: "v1", edgeIds: ["n0->n1", "n1->n0"] },
    ]);
    expect(screen.getByText(/not proven optimal/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel run" })).toHaveProperty("disabled", true);
  });

  it("cancels an active run via the API and shows the server's answer", async () => {
    useWorkspace.setState({ versionId: "ver-1", activeRunId: "run-1" });
    let run = makeRun({ status: "RUNNING", started_at: "x", attempt: 1 });
    const { calls } = installFetch({
      ...baseRoutes,
      "GET /api/v1/runs/run-1": () => run,
      "POST /api/v1/runs/run-1/cancel": () => {
        run = makeRun({ status: "CANCELLING", started_at: "x", attempt: 1 });
        return { id: "run-1", status: "CANCELLING" };
      },
    });
    renderCC();
    fireEvent.click(await screen.findByRole("button", { name: "Cancel run" }));
    await screen.findByRole("button", { name: "Cancelling…" });
    expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/cancel"))).toBe(true);
  });

  it("shows API validation errors from a rejected submission", async () => {
    useWorkspace.setState({ versionId: "ver-1" });
    installFetch({
      ...baseRoutes,
      "POST /api/v1/runs": () =>
        new Response(
          JSON.stringify({
            error: {
              code: "config_exceeds_limits",
              message: "configuration exceeds server limits",
            },
          }),
          { status: 422 },
        ),
    });
    renderCC();
    fireEvent.click(await screen.findByRole("button", { name: "Launch run" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("config_exceeds_limits");
    expect(useWorkspace.getState().activeRunId).toBeNull();
  });

  it("hides the seed field for a seedless solver", async () => {
    useWorkspace.setState({ versionId: "ver-1" });
    installFetch(baseRoutes);
    renderCC();
    fireEvent.change(await screen.findByLabelText("Algorithm"), {
      target: { value: "ortools_cvrp" },
    });
    expect(screen.queryByLabelText(/Seed/)).toBeNull();
    expect(screen.getByText("This solver takes no seed.")).toBeTruthy();
    expect((screen.getByLabelText(/Time limit/) as HTMLInputElement).value).toBe("2");
  });

  it("reports an unreachable API instead of rendering stale or fake data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    renderCC();
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0].textContent).toMatch(/Cannot reach the API/);
  });
});

describe("routesFromResult", () => {
  it("concatenates leg edge ids per vehicle exactly as stored", () => {
    expect(routesFromResult(result)).toEqual([{ vehicleId: "v1", edgeIds: ["n0->n1", "n1->n0"] }]);
    expect(routesFromResult(undefined)).toEqual([]);
  });
});
