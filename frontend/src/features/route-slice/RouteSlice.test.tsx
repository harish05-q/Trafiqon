import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { NetworkViewProps } from "@/features/network/NetworkView";
import type { ScenarioOut, ShortestPathResponse } from "@/lib/api/types";
import { RouteSlice } from "./RouteSlice";

// React Flow needs real layout; here we only check what the slice hands to the renderer.
const rendered: NetworkViewProps[] = [];
vi.mock("@/features/network/NetworkView", () => ({
  NetworkView: (props: NetworkViewProps) => {
    rendered.push(props);
    return <div data-testid="network" />;
  },
}));

const scenario: ScenarioOut = {
  id: "urban_grid",
  name: "Urban Grid",
  description: "",
  synthetic: true,
  settings: {},
  graph: {
    nodes: ["n0", "n1", "n2"].map((id, i) => ({ id, x: i, y: 0, label: null })),
    edges: [
      {
        id: "n0->n1",
        source: "n0",
        target: "n1",
        distance: 1,
        base_time: 2,
        current_time: 2,
        closed: false,
        road_class: null,
        capacity: null,
        congestion: null,
      },
      {
        id: "n1->n2",
        source: "n1",
        target: "n2",
        distance: 1,
        base_time: 3,
        current_time: 3,
        closed: false,
        road_class: null,
        capacity: null,
        congestion: null,
      },
    ],
  },
  depots: [{ id: "d1", node_id: "n0" }],
  customers: [{ id: "c1", node_id: "n2", demand: 1 }],
  vehicles: [],
};

const pathResponse: ShortestPathResponse = {
  scenario_id: "urban_grid",
  algorithm: "dijkstra",
  source: "n0",
  target: "n2",
  reachable: true,
  path: {
    node_ids: ["n0", "n1", "n2"],
    edge_ids: ["n0->n1", "n1->n2"],
    travel_time: 5,
    distance: 2,
  },
  expanded_nodes: 3,
  evaluator_version: "1",
};

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

function renderSlice() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RouteSlice />
    </QueryClientProvider>,
  );
}

describe("RouteSlice", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    rendered.length = 0;
    fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith("/api/v1/scenarios/builtin"))
        return json([
          {
            id: "urban_grid",
            name: "Urban Grid",
            description: "",
            synthetic: true,
            node_count: 3,
            edge_count: 2,
            customer_count: 1,
            vehicle_count: 0,
          },
        ]);
      if (url.endsWith("/api/v1/scenarios/builtin/urban_grid")) return json(scenario);
      if (url.endsWith("/api/v1/routing/shortest-path") && init?.method === "POST")
        return json(pathResponse);
      return json({ error: { code: "not_found", message: "nope" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("draws exactly the route returned by the API", async () => {
    renderSlice();
    const button = await screen.findByRole("button", { name: "Compute route" });
    expect(rendered.at(-1)?.pathEdgeIds).toEqual([]);

    fireEvent.click(button);

    await screen.findByTestId("travel-time");
    const request = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/shortest-path"))!;
    expect(JSON.parse(request[1].body)).toEqual({
      scenario_id: "urban_grid",
      source: "n0",
      target: "n2",
      algorithm: "dijkstra",
    });
    expect(rendered.at(-1)?.pathEdgeIds).toEqual(pathResponse.path!.edge_ids);
    expect(screen.getByTestId("travel-time").textContent).toBe("5.00 min");
    const items = within(screen.getByTestId("route-edges")).getAllByRole("listitem");
    expect(items.map((li) => li.dataset.edgeId)).toEqual(["n0->n1", "n1->n2"]);
    expect(screen.getByText(/Synthetic scenario/)).toBeTruthy();
  });

  it("shows unreachable results without drawing a route", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/shortest-path") && init?.method === "POST")
        return json({ ...pathResponse, reachable: false, path: null });
      if (url.endsWith("/builtin"))
        return json([
          {
            id: "urban_grid",
            name: "Urban Grid",
            description: "",
            synthetic: true,
            node_count: 3,
            edge_count: 2,
            customer_count: 1,
            vehicle_count: 0,
          },
        ]);
      return json(scenario);
    });
    renderSlice();
    fireEvent.click(await screen.findByRole("button", { name: "Compute route" }));
    expect(await screen.findByText(/Unreachable/)).toBeTruthy();
    expect(rendered.at(-1)?.pathEdgeIds).toEqual([]);
  });

  it("shows API errors", async () => {
    fetchMock.mockImplementation(() =>
      json({ error: { code: "internal_error", message: "boom" } }, 500),
    );
    renderSlice();
    expect((await screen.findByRole("alert")).textContent).toBe("boom");
  });
});
