// SPEC_FULL 16 end-to-end workflows 1-4, against the real API, worker and database.
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { API_URL } from "./stack";

const api = (p: string) => `${API_URL}/api/v1${p}`;

async function importBuiltin(request: APIRequestContext, name: string, builtin = "urban_grid") {
  const r = await request.post(api("/scenarios"), { data: { name, builtin_id: builtin } });
  expect(r.status()).toBe(201);
  return (await r.json()) as { id: string; current_version_id: string };
}

async function waitForRun(request: APIRequestContext, runId: string, status: string) {
  await expect
    .poll(async () => (await (await request.get(api(`/runs/${runId}`))).json()).status, {
      timeout: 60_000,
    })
    .toBe(status);
}

async function activeRunId(page: Page): Promise<string> {
  return page.evaluate(
    () => JSON.parse(localStorage.getItem("trafiqon.workspace.v2")!).state.activeRunId as string,
  );
}

async function selectSaved(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).click();
  await expect(page.getByRole("figure", { name: /Road network of/ })).toBeVisible();
}

async function launch(
  page: Page,
  algorithm: string,
  budget: Record<string, string>,
  seed?: string,
) {
  await page.getByLabel("Algorithm", { exact: true }).selectOption(algorithm);
  for (const [label, value] of Object.entries(budget)) await page.getByLabel(label).fill(value);
  if (seed !== undefined) await page.getByLabel(/^Seed/).fill(seed);
  await page.getByRole("button", { name: "Launch run" }).click();
}

test("1: load a built-in scenario, run an algorithm, inspect the result", async ({
  page,
  request,
}) => {
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Import Urban Grid as a saved scenario" }).click();
  const network = page.getByRole("figure", { name: /Road network of Urban Grid/ });
  await expect(network).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(30);
  await expect(page.locator("[data-edge-id]")).toHaveCount(80);
  await expect(page.getByRole("banner")).toContainText("Urban Grid v1 · synthetic");

  await launch(page, "simulated_annealing", { "Iterations (moves)": "5000" }, "11");
  const active = page.getByRole("region", { name: "Active run" });
  await expect(active).toContainText("COMPLETED");

  const runId = await activeRunId(page);
  const result = await (await request.get(api(`/runs/${runId}/result`))).json();
  const best = page.getByRole("region", { name: "Best solution" });
  await expect(best).toContainText(result.objective.toFixed(3));
  await expect(best).toContainText("not proven optimal");

  // The drawn route edges are exactly the stored evaluator legs.
  const stored = new Set<string>(
    result.evaluation.routes.flatMap((r: { legs: { edge_ids: string[] }[] }) =>
      r.legs.flatMap((l) => l.edge_ids),
    ),
  );
  const drawn = await page
    .locator("[data-edge-id]:has(.road-edge.on-route)")
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-edge-id")));
  expect(new Set(drawn)).toEqual(stored);

  // Inspect one vehicle route.
  const firstRoute = result.evaluation.routes[0];
  await best.getByRole("button", { name: new RegExp(`^${firstRoute.vehicle_id} ·`) }).click();
  const inspector = page.getByRole("region", { name: "Inspector" });
  await expect(inspector).toContainText(`Vehicle${firstRoute.vehicle_id}`);
  await expect(inspector).toContainText(firstRoute.customer_ids.join(" → "));
});

test("2: modify a scenario, save a version, run against that version", async ({
  page,
  request,
}) => {
  const name = `E2E edit ${Date.now()}`;
  const created = await importBuiltin(request, name);
  await page.goto("/scenario-studio");
  const saved = page.getByLabel("Load a saved scenario");
  await expect(saved.locator("option", { hasText: name })).toHaveCount(1);
  await saved.selectOption({ label: name });
  await expect(page.getByText(/from v1; saving creates a new version/)).toBeVisible();

  // Close the road n0_1 -> n0_2 by clicking it on the canvas.
  await page.locator('[data-edge-id="n0_1->n0_2"] .road-edge-hit').click({ force: true });
  await expect(page.getByText(/Road n0_1->n0_2/)).toBeVisible();
  await page.getByLabel(/Closed \(never used by routing\)/).check();
  await page.getByLabel("Version note").fill("close n0_1->n0_2");
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText(/Valid\. No infeasibility detected/)).toBeVisible();
  await page.getByRole("button", { name: "Save new version" }).click();
  await expect(page.getByText(/Saved as an immutable version/)).toBeVisible();

  const detail = await (await request.get(api(`/scenarios/${created.id}`))).json();
  expect(detail.versions.map((v: { version_number: number }) => v.version_number)).toEqual([1, 2]);
  const v2 = detail.versions[1].id;
  const v2data = await (await request.get(api(`/scenario-versions/${v2}`))).json();
  expect(v2data.data.graph.edges.find((e: { id: string }) => e.id === "n0_1->n0_2").closed).toBe(
    true,
  );

  await page.getByRole("link", { name: "Run it in the Command Center" }).click();
  await expect(page.getByRole("banner")).toContainText(`${name} v2`);
  await launch(page, "simulated_annealing", { "Iterations (moves)": "3000" }, "3");
  await expect(page.getByRole("region", { name: "Active run" })).toContainText("COMPLETED");
  const runId = await activeRunId(page);
  const run = await (await request.get(api(`/runs/${runId}`))).json();
  expect(run.scenario_version_id).toBe(v2);
  const result = await (await request.get(api(`/runs/${runId}/result`))).json();
  const used = result.evaluation.routes.flatMap((r: { legs: { edge_ids: string[] }[] }) =>
    r.legs.flatMap((l) => l.edge_ids),
  );
  expect(used).not.toContain("n0_1->n0_2");
});

test("3: start a run, observe progress, cancel it, verify the terminal state", async ({
  page,
  request,
}) => {
  const name = `E2E cancel ${Date.now()}`;
  await importBuiltin(request, name, "congested_city");
  await page.goto("/command-center");
  await selectSaved(page, name);
  await launch(page, "simulated_annealing", { "Iterations (moves)": "2000000" }, "1");
  const active = page.getByRole("region", { name: "Active run" });
  await expect(active).toContainText("RUNNING");
  // Real progress from the worker (iteration counter moves past zero).
  await expect(active.locator("dd").first()).not.toHaveText("–");
  await expect(active.getByText(/iteration \d+ · best/).first()).toBeVisible();

  await active.getByRole("button", { name: "Cancel run" }).click();
  await expect(active).toContainText("CANCELLED");
  const runId = await activeRunId(page);
  const run = await (await request.get(api(`/runs/${runId}`))).json();
  expect(run.status).toBe("CANCELLED");
  expect(run.termination_reason).toBe("cancelled");
  // Terminal state is stable: a second cancel changes nothing.
  const again = await request.post(api(`/runs/${runId}/cancel`));
  expect((await again.json()).status).toBe("CANCELLED");
  await expect(page.getByRole("region", { name: "Best solution" })).toContainText(
    "stopped: cancelled",
  );
});

test("4: compare multiple completed algorithm runs", async ({ page, request }) => {
  const name = `E2E compare ${Date.now()}`;
  const s = await importBuiltin(request, name, "incident_response");
  const ids: string[] = [];
  for (const body of [
    { algorithm_id: "simulated_annealing", config: { max_iterations: 3000 }, seed: 1 },
    { algorithm_id: "qpso_hybrid", config: { iterations: 5, swarm_size: 6 }, seed: 2 },
  ]) {
    const r = await request.post(api("/runs"), {
      data: { scenario_version_id: s.current_version_id, ...body },
    });
    expect(r.status()).toBe(202);
    ids.push((await r.json()).id);
  }
  for (const id of ids) await waitForRun(request, id, "COMPLETED");
  const objectives = await Promise.all(
    ids.map(
      async (id) =>
        (await (await request.get(api(`/runs/${id}/result`))).json()).objective as number,
    ),
  );

  await page.goto("/experiments");
  await expect
    .poll(() => page.evaluate(() => document.documentElement.dataset.theme))
    .toBe("light");
  await page.getByLabel("Scenario").selectOption({ label: name });
  for (const id of ids) await page.getByLabel(`Compare run ${id.slice(0, 8)}`).check();
  const table = page.getByRole("table", { name: "Run comparison" });
  for (const o of objectives) await expect(table).toContainText(o.toFixed(3));
  await expect(table).toContainText("simulated_annealing v1");
  await expect(table).toContainText("qpso_hybrid v1");
  await expect(page.getByText(/different budget units/)).toBeVisible();
  await expect(page.getByRole("img", { name: /compared runs/ })).toBeVisible();
});
