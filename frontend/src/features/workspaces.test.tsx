// Component tests for the M6 workspaces against real-shaped API responses (fake fetch).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StudioCanvasProps } from "@/features/scenario-studio/StudioCanvas";
import { useWorkspace } from "@/stores/workspace";
import {
  FakeEventSource,
  algorithms,
  installFetch,
  makeRun,
  result,
  savedScenario,
  scenarioData,
  version,
} from "@/test/fake-api";
import { AlgorithmLab } from "./algorithm-lab/AlgorithmLab";
import { ExperimentExplorer } from "./experiments/ExperimentExplorer";
import { ScenarioStudio } from "./scenario-studio/ScenarioStudio";

vi.mock("@/components/charts/ConvergenceChart", () => ({
  ConvergenceChart: (p: { series: { name: string; points: unknown[] }[] }) => (
    <div data-testid="chart">{p.series.map((s) => `${s.name}:${s.points.length}`).join("|")}</div>
  ),
  SeedChart: (p: { runs: unknown[]; specs: string[] }) => (
    <div data-testid="seed-chart">
      {p.specs.join(",")}:{p.runs.length}
    </div>
  ),
}));
let canvas: StudioCanvasProps | null = null;
vi.mock("@/features/scenario-studio/StudioCanvas", () => ({
  StudioCanvas: (p: StudioCanvasProps) => {
    canvas = p;
    return <div data-testid="studio-canvas">{p.data.graph.nodes.length} nodes</div>;
  },
}));

function renderWith(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const common = {
  "GET /api/v1/algorithms": () => algorithms,
  "GET /api/v1/scenarios": () => ({ items: [savedScenario], total: 1, limit: 50, offset: 0 }),
  "GET /api/v1/scenarios/builtin": () => [
    {
      id: "urban_grid",
      name: "Urban Grid",
      description: "",
      synthetic: true,
      node_count: 2,
      edge_count: 2,
      customer_count: 1,
      vehicle_count: 1,
    },
  ],
  "GET /api/v1/scenario-versions/ver-1": () => version,
  "GET /api/v1/runs": () => ({ items: [], total: 0, limit: 20, offset: 0 }),
};

beforeEach(() => {
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

describe("Algorithm Lab", () => {
  it("submits only changed parameters and shows feasibility from the server", async () => {
    useWorkspace.setState({ versionId: "ver-1" });
    const { calls } = installFetch({
      ...common,
      "POST /api/v1/scenarios/validate": () => ({
        valid: true,
        feasible_so_far: true,
        issues: [],
        strongly_connected_components: 1,
        unreachable_location_pairs: 0,
        total_demand: 3,
        total_capacity: 10,
      }),
      "POST /api/v1/runs": () => makeRun(),
      "GET /api/v1/runs/run-1": () => makeRun(),
    });
    renderWith(<AlgorithmLab />);
    await screen.findByText(/No infeasibility detected/);
    fireEvent.change(await screen.findByLabelText("iterations"), { target: { value: "40" } });
    fireEvent.change(screen.getByLabelText(/^Seed/), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit run" }));
    await waitFor(() => expect(useWorkspace.getState().activeRunId).toBe("run-1"));
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/v1/runs")!;
    expect(post.body).toEqual({
      scenario_version_id: "ver-1",
      algorithm_id: "qpso_hybrid",
      config: { iterations: 40 },
      seed: 5,
    });
    const validate = calls.find((c) => c.path === "/api/v1/scenarios/validate")!;
    expect(validate.body).not.toHaveProperty("id");
  });

  it("blocks submission while a parameter is out of range", async () => {
    useWorkspace.setState({ versionId: "ver-1" });
    installFetch({
      ...common,
      "POST /api/v1/scenarios/validate": () => new Response("{}", { status: 500 }),
    });
    renderWith(<AlgorithmLab />);
    fireEvent.change(await screen.findByLabelText("swarm_size"), { target: { value: "500" } });
    expect(screen.getByRole("button", { name: "Submit run" })).toHaveProperty("disabled", true);
    expect(
      screen
        .getAllByRole("alert")
        .some((a) => /swarm_size: must be ≤ 100/.test(a.textContent ?? "")),
    ).toBe(true);
  });

  it("plots stored history, labels stored configuration and diagnostics", async () => {
    useWorkspace.setState({ versionId: "ver-1", activeRunId: "run-1" });
    const done = makeRun({
      status: "COMPLETED",
      started_at: "x",
      config: { iterations: 40, swarm_size: 20 },
    });
    installFetch({
      ...common,
      "POST /api/v1/scenarios/validate": () => ({
        valid: true,
        feasible_so_far: false,
        issues: [
          {
            code: "insufficient_fleet_capacity",
            message: "too much demand",
            severity: "infeasible",
            ref: null,
          },
        ],
        strongly_connected_components: 1,
        unreachable_location_pairs: 0,
        total_demand: 30,
        total_capacity: 10,
      }),
      "GET /api/v1/runs/run-1": () => done,
      "GET /api/v1/runs/run-1/result": () => ({
        ...result,
        history: [
          { iteration: 1, evaluations: 1, elapsed_s: 0.1, current_objective: 5, best_objective: 5 },
        ],
        diagnostics: { diversity: [0.4, 0.1], repairs_failed: 0, software: { python: "3.12" } },
      }),
    });
    renderWith(<AlgorithmLab />);
    await waitFor(() =>
      expect(screen.getByTestId("chart").textContent).toMatch(/stored history\):1/),
    );
    expect(await screen.findByText(/Infeasibility detected/)).toBeTruthy();
    expect(screen.getByText("2 values: 0.4000 → 0.1000")).toBeTruthy();
    const config = screen.getByRole("region", { name: "Resolved configuration (stored)" });
    expect(within(config).getByText("40")).toBeTruthy();
  });
});

describe("Scenario Studio", () => {
  it("copies a built-in, edits it, validates on the server and saves a new scenario", async () => {
    const { calls } = installFetch({
      ...common,
      "GET /api/v1/scenarios/builtin/urban_grid": () => scenarioData,
      "POST /api/v1/scenarios/validate": () => ({
        valid: true,
        feasible_so_far: true,
        issues: [],
        strongly_connected_components: 1,
        unreachable_location_pairs: 0,
        total_demand: 3,
        total_capacity: 10,
      }),
      "POST /api/v1/scenarios": () => ({
        ...savedScenario,
        id: "s2",
        current_version_id: "ver-2",
        versions: [],
      }),
    });
    renderWith(<ScenarioStudio />);
    const builtinSelect = await screen.findByLabelText("Copy a built-in scenario");
    await within(builtinSelect).findByRole("option", { name: "Urban Grid" });
    fireEvent.change(builtinSelect, { target: { value: "urban_grid" } });
    await screen.findByText("2 nodes");
    act(() => canvas!.onAddNode(2, 0));
    await screen.findByText("3 nodes");
    // Add a road with the road tool: origin, then destination.
    fireEvent.click(screen.getByRole("button", { name: "Add road" }));
    act(() => canvas!.onNodeClick("n1"));
    act(() => canvas!.onNodeClick("n2"));
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByText(/No infeasibility detected/);
    fireEvent.click(screen.getByRole("button", { name: "Save scenario" }));
    await waitFor(() => expect(useWorkspace.getState().versionId).toBe("ver-2"));
    const saved = calls.find((c) => c.method === "POST" && c.path === "/api/v1/scenarios")!
      .body as {
      name: string;
      data: typeof scenarioData;
    };
    expect(saved.name).toBe("Urban Grid (edited)");
    expect(saved.data.graph.nodes).toHaveLength(3);
    expect(saved.data.graph.edges.map((e) => e.id)).toContain("n1->n2");
    expect(saved.data).not.toHaveProperty("id");
    expect(await screen.findByText(/Saved as an immutable version/)).toBeTruthy();
  });

  it("edits a saved scenario's road and saves a new version; rejected edits are explained", async () => {
    const { calls } = installFetch({
      ...common,
      "GET /api/v1/scenarios/s1": () => ({ ...savedScenario, versions: [] }),
      "POST /api/v1/scenarios/s1/versions": () => ({ ...version, id: "ver-9", version_number: 2 }),
    });
    renderWith(<ScenarioStudio />);
    const savedSelect = await screen.findByLabelText("Load a saved scenario");
    await within(savedSelect).findByRole("option", { name: "Urban Grid" });
    fireEvent.change(savedSelect, { target: { value: "s1" } });
    await screen.findByText(/from v1/);
    expect(screen.getByRole("button", { name: "Save new version" })).toHaveProperty(
      "disabled",
      true,
    );
    act(() => canvas!.onEdgeClick("n0->n1"));
    fireEvent.click(await screen.findByLabelText(/Closed/));
    fireEvent.change(screen.getByLabelText(/Current time/), { target: { value: "-3" } });
    fireEvent.blur(screen.getByLabelText(/Current time/));
    expect((await screen.findByRole("alert")).textContent).toMatch(/current_time must be/);
    fireEvent.click(screen.getByRole("button", { name: "Save new version" }));
    await waitFor(() => expect(useWorkspace.getState().versionId).toBe("ver-9"));
    const body = calls.find((c) => c.path === "/api/v1/scenarios/s1/versions")!.body as {
      data: typeof scenarioData;
    };
    expect(body.data.graph.edges.find((e) => e.id === "n0->n1")!.closed).toBe(true);
  });

  it("surfaces server-side save errors", async () => {
    installFetch({
      ...common,
      "POST /api/v1/scenarios": () =>
        new Response(
          JSON.stringify({
            error: { code: "invalid_scenario", message: "scenario failed validation" },
          }),
          { status: 422 },
        ),
    });
    renderWith(<ScenarioStudio />);
    fireEvent.click(await screen.findByRole("button", { name: "Save scenario" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/scenario failed validation/);
  });
});

describe("Experiment Explorer", () => {
  it("compares selected runs side by side from stored results", async () => {
    const a = makeRun({
      id: "run-a",
      status: "COMPLETED",
      started_at: "x",
      algorithm_id: "qpso_hybrid",
      seed: 1,
    });
    const b = makeRun({
      id: "run-b",
      status: "COMPLETED",
      started_at: "x",
      algorithm_id: "simulated_annealing",
      seed: 2,
    });
    const { calls } = installFetch({
      ...common,
      "GET /api/v1/runs": () => ({ items: [a, b], total: 2, limit: 25, offset: 0 }),
      "GET /api/v1/runs/run-a": () => a,
      "GET /api/v1/runs/run-b": () => b,
      "GET /api/v1/runs/run-a/result": () => ({ ...result, run_id: "run-a", objective: 70.5 }),
      "GET /api/v1/runs/run-b/result": () => ({ ...result, run_id: "run-b", objective: 72.25 }),
    });
    renderWith(<ExperimentExplorer />);
    fireEvent.click(await screen.findByLabelText("Compare run run-a"));
    fireEvent.click(screen.getByLabelText("Compare run run-b"));
    const table = await screen.findByRole("table", { name: "Run comparison" });
    await within(table).findByText("70.500");
    expect(within(table).getByText("72.250")).toBeTruthy();
    expect(screen.getByText(/different budget units/)).toBeTruthy();
    // Filters go to the API.
    fireEvent.change(screen.getByLabelText("Algorithm"), { target: { value: "qpso_hybrid" } });
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/v1/runs" && c.method === "GET")).toBe(true),
    );
  });

  it("shows suite statistics with a labelled heuristic reference and export links", async () => {
    const suite = {
      id: "suite-1",
      name: "Baseline",
      scenario_version_id: "ver-1",
      specs: [
        {
          label: "simulated_annealing",
          algorithm_id: "simulated_annealing",
          algorithm_version: "1",
          config: {},
        },
      ],
      seeds: [0, 1],
      repetitions: 2,
      budget_policy: "SA 20000 moves",
      created_at: "2026-10-28T00:00:00Z",
      status_counts: { COMPLETED: 2 },
      run_ids: ["r1", "r2"],
    };
    installFetch({
      ...common,
      "GET /api/v1/suites": () => ({ items: [suite], total: 1, limit: 50, offset: 0 }),
      "GET /api/v1/suites/suite-1": () => suite,
      "GET /api/v1/suites/suite-1/comparison": () => ({
        metadata: {},
        quantity_kinds: {},
        complete: true,
        reference: {
          kind: "best_observed_heuristic",
          objective: 70,
          source_spec: "simulated_annealing",
          source_seed: 0,
          source_repetition: 0,
        },
        summaries: [
          {
            spec: "simulated_annealing",
            algorithm_id: "simulated_annealing",
            n: 2,
            feasible_count: 2,
            feasible_rate: 1,
            objective_mean: 71,
            objective_median: 71,
            objective_std: 1.41421,
            objective_best: 70,
            objective_worst: 72,
            elapsed_mean_s: 0.2,
            elapsed_median_s: 0.2,
            gap_mean_percent: 1.43,
          },
        ],
        status_counts_by_spec: { simulated_annealing: { COMPLETED: 2 } },
        runs: [
          {
            spec: "simulated_annealing",
            algorithm_id: "simulated_annealing",
            seed: 0,
            repetition: 0,
            feasible: true,
            objective: 70,
            elapsed_s: 0.2,
            termination_reason: "iteration_limit",
          },
          {
            spec: "simulated_annealing",
            algorithm_id: "simulated_annealing",
            seed: 1,
            repetition: 1,
            feasible: true,
            objective: 72,
            elapsed_s: 0.2,
            termination_reason: "iteration_limit",
          },
        ],
      }),
    });
    renderWith(<ExperimentExplorer />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Benchmark suites" }));
    fireEvent.click(await screen.findByRole("button", { name: /Baseline/ }));
    expect(await screen.findByText("best observed heuristic (not an optimum)")).toBeTruthy();
    const stats = screen.getByRole("table", { name: "Suite statistics" });
    expect(within(stats).getByText("1.414")).toBeTruthy();
    expect(within(stats).getByText("2/2")).toBeTruthy();
    expect(screen.getByTestId("seed-chart").textContent).toBe("simulated_annealing:2");
    expect(screen.getByRole("link", { name: /Export CSV/ }).getAttribute("href")).toMatch(
      /suites\/suite-1\/export\?format=csv$/,
    );
    expect(screen.getByRole("link", { name: /Export JSON/ }).getAttribute("href")).toMatch(
      /format=json$/,
    );
  });
});
