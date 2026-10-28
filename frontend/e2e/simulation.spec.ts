// SPEC_FULL 16 end-to-end workflow 5: advance a simulation, introduce an incident and verify a
// valid remaining-route replanning workflow (against the real API, worker and database).
import { expect, test } from "@playwright/test";

import { API_URL } from "./stack";

const api = (p: string) => `${API_URL}/api/v1${p}`;

type Vehicle = {
  id: string;
  node: string | null;
  edge_id: string | null;
  progress: number | null;
  completed: { customer_id: string; time: number }[];
  remaining_edge_ids: string[];
};

test("5: advance a simulation, add an incident, replan the remaining routes", async ({
  page,
  request,
}) => {
  const name = `E2E sim ${Date.now()}`;
  const scenario = await (
    await request.post(api("/scenarios"), { data: { name, builtin_id: "urban_grid" } })
  ).json();
  const run = await (
    await request.post(api("/runs"), {
      data: {
        scenario_version_id: scenario.current_version_id,
        algorithm_id: "simulated_annealing",
        config: { max_iterations: 3000 },
        seed: 5,
      },
    })
  ).json();
  await expect
    .poll(async () => (await (await request.get(api(`/runs/${run.id}`))).json()).status, {
      timeout: 60_000,
    })
    .toBe("COMPLETED");

  await page.goto("/command-center");
  await page.getByRole("button", { name, exact: true }).click();
  await page
    .getByRole("region", { name: "Runs on this version" })
    .getByRole("button")
    .first()
    .click();
  const simulate = page.getByRole("button", { name: /Simulate the active run/ });
  await expect(simulate).toBeEnabled();
  await simulate.click();
  const panel = page.getByRole("region", { name: "Simulation" });
  await expect(panel).toContainText("ready");
  const simId = await page.evaluate(
    () => JSON.parse(localStorage.getItem("trafiqon.workspace.v2")!).state.simulationId as string,
  );

  // Advance 6 ticks (3 simulated minutes) with the Step control.
  for (let i = 0; i < 6; i++) await panel.getByRole("button", { name: "Step" }).click();
  await expect(panel).toContainText("0:03.0");
  await expect(page.locator(".vehicle-marker")).not.toHaveCount(0);

  let state = await (await request.get(api(`/simulations/${simId}`))).json();
  expect(state.tick).toBe(6);
  const target: Vehicle = state.vehicles.find((v: Vehicle) => v.remaining_edge_ids.length > 3);
  const blocked = target.remaining_edge_ids[2]; // a road the vehicle has not reached yet

  // Close that road from the map's road actions.
  await page.locator(`[data-edge-id="${blocked}"] .road-edge-hit`).click({ force: true });
  const actions = page.getByLabel("Simulation road actions");
  await expect(actions).toContainText(`planned by ${target.id}`);
  await actions.getByRole("button", { name: "Incident: close road" }).click();
  await expect(panel.getByRole("list", { name: "Incidents" })).toContainText(blocked);

  const before = await (await request.get(api(`/simulations/${simId}`))).json();
  expect(before.road_overrides.find((o: { edge_id: string }) => o.edge_id === blocked).closed).toBe(
    true,
  );

  await panel.getByRole("button", { name: "Replan" }).click();
  await expect(panel.getByLabel("Last replan")).toContainText("latency");
  state = await (await request.get(api(`/simulations/${simId}`))).json();

  // Replanning kept the clock, every position and every completed stop.
  expect(state.tick).toBe(before.tick);
  expect(state.time_min).toBe(before.time_min);
  expect(state.plan_version).toBe(1);
  for (const v of state.vehicles as Vehicle[]) {
    const b = (before.vehicles as Vehicle[]).find((x) => x.id === v.id)!;
    expect([v.node, v.edge_id, v.progress, v.completed]).toEqual([
      b.node,
      b.edge_id,
      b.progress,
      b.completed,
    ]);
  }
  // ...and the remaining plan avoids the closed road.
  for (const v of state.vehicles as Vehicle[]) expect(v.remaining_edge_ids).not.toContain(blocked);
  expect(state.last_replan.unserved).toEqual([]);

  // Run to completion in real time: every customer served, nobody drove the closed road after.
  await panel.getByLabel("Speed").selectOption("30");
  await panel.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("banner")).toContainText("Simulation: finished", { timeout: 30_000 });
  state = await (await request.get(api(`/simulations/${simId}`))).json();
  expect(state.status).toBe("finished");
  expect(state.served_count).toBe(state.customer_count);
  const served = (state.vehicles as Vehicle[])
    .flatMap((v) => v.completed.map((c) => c.customer_id))
    .sort();
  expect(new Set(served).size).toBe(state.customer_count);
});
