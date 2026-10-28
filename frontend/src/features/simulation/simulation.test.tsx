import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CommandCenter } from "@/features/command-center/CommandCenter";
import type { RouteOverlay } from "@/features/network/toFlow";
import { useWorkspace } from "@/stores/workspace";
import {
  FakeEventSource,
  algorithms,
  installFetch,
  makeRun,
  result,
  savedScenario,
  scenarioData,
  simState,
  version,
} from "@/test/fake-api";
import {
  effectiveScenario,
  formatSimTime,
  simRoutes,
  vehicleMarkers,
  type VehicleMarker,
} from "./simView";

const canvas: {
  routes?: RouteOverlay[];
  vehicles?: VehicleMarker[];
  scenario: typeof scenarioData;
}[] = [];
vi.mock("@/features/network/NetworkCanvas", () => ({
  NetworkCanvas: (p: (typeof canvas)[number]) => {
    canvas.push(p);
    return <div data-testid="network" />;
  },
}));

describe("simView", () => {
  it("applies road overrides from the simulation without mutating the scenario", () => {
    const sim = simState({
      road_overrides: [
        {
          edge_id: "n0->n1",
          closed: true,
          current_time: 6,
          original_current_time: 2,
          original_closed: false,
        },
      ],
    });
    const eff = effectiveScenario(scenarioData, sim);
    const e = eff.graph.edges.find((x) => x.id === "n0->n1")!;
    expect(e).toMatchObject({ closed: true, current_time: 6, congestion: 3 });
    expect(scenarioData.graph.edges[0].closed).toBe(false);
    expect(effectiveScenario(scenarioData, simState())).toBe(scenarioData);
  });

  it("routes are the remaining planned edges; markers are backend positions", () => {
    const sim = simState();
    expect(simRoutes(sim)).toEqual([{ vehicleId: "v1", edgeIds: ["n0->n1", "n1->n0"] }]);
    expect(vehicleMarkers(sim)).toEqual([
      expect.objectContaining({ id: "v1", x: 0.25, y: 0, status: "en_route" }),
    ]);
    const noPos = simState({ vehicles: [{ ...sim.vehicles[0], x: null, y: null }] });
    expect(vehicleMarkers(noPos)).toEqual([]); // no invented positions
  });

  it("formats the simulated clock", () => {
    expect(formatSimTime(0)).toBe("0:00.0");
    expect(formatSimTime(75.5)).toBe("1:15.5");
  });
});

function renderCC() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CommandCenter />
    </QueryClientProvider>,
  );
}

const done = makeRun({ status: "COMPLETED", started_at: "x", attempt: 1 });
const routes = {
  "GET /api/v1/scenarios": () => ({ items: [savedScenario], total: 1, limit: 50, offset: 0 }),
  "GET /api/v1/scenarios/builtin": () => [],
  "GET /api/v1/algorithms": () => algorithms,
  "GET /api/v1/scenario-versions/ver-1": () => version,
  "GET /api/v1/runs": () => ({ items: [done], total: 1, limit: 20, offset: 0 }),
  "GET /api/v1/runs/run-1": () => done,
  "GET /api/v1/runs/run-1/result": () => result,
};

describe("Simulation in the Command Center", () => {
  beforeEach(() => {
    canvas.length = 0;
    vi.stubGlobal("EventSource", FakeEventSource);
    useWorkspace.setState({
      versionId: "ver-1",
      activeRunId: "run-1",
      compareRunId: null,
      simulationId: null,
      selection: null,
    });
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("creates a session from the active run and draws backend vehicles and remaining paths", async () => {
    const { calls } = installFetch({
      ...routes,
      "POST /api/v1/simulations": () => simState(),
      "GET /api/v1/simulations/sim-1": () => simState(),
    });
    renderCC();
    const simulate = await screen.findByRole("button", { name: /Simulate the active run/ });
    await waitFor(() => expect(simulate).toHaveProperty("disabled", false)); // run loaded
    fireEvent.click(simulate);
    await waitFor(() => expect(useWorkspace.getState().simulationId).toBe("sim-1"));
    expect(calls.find((c) => c.path === "/api/v1/simulations")!.body).toEqual({
      scenario_version_id: "ver-1",
      run_id: "run-1",
    });
    await waitFor(() => expect(canvas.at(-1)!.vehicles).toHaveLength(1));
    expect(canvas.at(-1)!.routes).toEqual([{ vehicleId: "v1", edgeIds: ["n0->n1", "n1->n0"] }]);
    expect(screen.getByText("0/1")).toBeTruthy();
  });

  it("sends control commands and shows the server's state, replan report and incidents", async () => {
    useWorkspace.setState({ simulationId: "sim-1" });
    let state = simState();
    const { calls } = installFetch({
      ...routes,
      "GET /api/v1/simulations/sim-1": () => state,
      "POST /api/v1/simulations/sim-1/control": (_u, init) => {
        const body = JSON.parse(String(init!.body));
        state = simState({
          status: body.action === "step" ? "ready" : "paused",
          tick: body.action === "step" ? 1 : 0,
          time_min: body.action === "step" ? 0.5 : 0,
        });
        return state;
      },
      "POST /api/v1/simulations/sim-1/replan": () => ({
        replan: null,
        state: (state = simState({
          plan_version: 1,
          last_replan: {
            plan_version: 1,
            time: 0.5,
            tick: 1,
            latency_ms: 1.234,
            stops_reordered: 2,
            edges_changed: 5,
            unserved: ["c9"],
            vehicles: [
              {
                vehicle_id: "v1",
                old_stops: [],
                new_stops: [],
                unserved: ["c9"],
                end_depot_reachable: false,
                stops_reordered: 2,
                edges_changed: 5,
                remaining_time_min: null,
              },
            ],
          },
          incidents: [
            {
              id: "inc-1",
              kind: "closure",
              edge_ids: ["n0->n1"],
              factor: 1,
              created_at: 0.5,
              resolved_at: null,
              active: true,
            },
          ],
        })),
      }),
      "POST /api/v1/simulations/sim-1/incidents/inc-1/resolve": () =>
        (state = simState({
          incidents: [
            {
              id: "inc-1",
              kind: "closure",
              edge_ids: ["n0->n1"],
              factor: 1,
              created_at: 0.5,
              resolved_at: 1,
              active: false,
            },
          ],
        })),
    });
    renderCC();
    fireEvent.click(await screen.findByRole("button", { name: "Step" }));
    await screen.findByText("0:00.5");
    expect(calls.find((c) => c.path.endsWith("/control"))!.body).toEqual({
      action: "step",
      ticks: 1,
    });
    fireEvent.change(screen.getByLabelText("Speed"), { target: { value: "5" } });
    await waitFor(() =>
      expect(calls.filter((c) => c.path.endsWith("/control")).at(-1)!.body).toEqual({
        action: "speed",
        speed: 5,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Replan" }));
    const report = await screen.findByLabelText("Last replan");
    expect(report.textContent).toMatch(/latency 1\.23 ms \(measured\)/);
    expect(report.textContent).toMatch(/Unreachable, not served: c9/);
    expect(report.textContent).toMatch(/v1 cannot reach its end depot/);
    const incidents = screen.getByRole("list", { name: "Incidents" });
    fireEvent.click(within(incidents).getByRole("button", { name: "Resolve" }));
    await waitFor(() =>
      expect(within(incidents).queryByRole("button", { name: "Resolve" })).toBeNull(),
    );
  });

  it("road actions on a selected edge create incidents and change traffic", async () => {
    useWorkspace.setState({ simulationId: "sim-1", selection: { kind: "edge", id: "n0->n1" } });
    const { calls } = installFetch({
      ...routes,
      "GET /api/v1/simulations/sim-1": () => simState(),
      "POST /api/v1/simulations/sim-1/incidents": () => simState(),
      "POST /api/v1/simulations/sim-1/roads": () => simState({ traffic_factors: { "n0->n1": 3 } }),
    });
    renderCC();
    const actions = await screen.findByLabelText("Simulation road actions");
    expect(actions.textContent).toMatch(/planned by v1/);
    fireEvent.click(within(actions).getByRole("button", { name: "Incident: close road" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/incidents"))!.body).toEqual({
        edge_ids: ["n0->n1"],
        kind: "closure",
      }),
    );
    fireEvent.change(within(actions).getByLabelText("Traffic factor"), { target: { value: "3" } });
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/roads"))!.body).toEqual({
        edge_id: "n0->n1",
        traffic_factor: 3,
      }),
    );
  });

  it("inspector shows the simulation's road conditions, not the original ones", async () => {
    useWorkspace.setState({ simulationId: "sim-1", selection: { kind: "edge", id: "n0->n1" } });
    installFetch({
      ...routes,
      "GET /api/v1/simulations/sim-1": () =>
        simState({
          road_overrides: [
            {
              edge_id: "n0->n1",
              closed: true,
              current_time: 2,
              original_current_time: 2,
              original_closed: false,
            },
          ],
        }),
    });
    renderCC();
    const inspector = await screen.findByRole("region", { name: "Inspector" });
    await waitFor(() =>
      expect(within(inspector).getByText("Status").nextSibling!.textContent).toMatch(/closed/),
    );
  });

  it("forgets a session the backend no longer has", async () => {
    useWorkspace.setState({ simulationId: "gone" });
    installFetch(routes);
    renderCC();
    expect(await screen.findByText(/previous session is gone/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Simulate a construction plan/ })).toBeTruthy();
  });
});
