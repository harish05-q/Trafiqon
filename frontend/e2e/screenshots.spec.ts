// Visual capture of each workspace with real data (for human review; asserts only basics).
// Screenshots are written to test-results/screens/ (git-ignored).
import { expect, test } from "@playwright/test";

import { API_URL } from "./stack";

const api = (p: string) => `${API_URL}/api/v1${p}`;

test("capture workspaces", async ({ page, request }) => {
  const s = await (
    await request.post(api("/scenarios"), {
      data: { name: `Screens ${Date.now()}`, builtin_id: "congested_city" },
    })
  ).json();
  await page.goto("/command-center");
  await page.getByRole("button", { name: s.name, exact: true }).click();
  await page.getByLabel("Algorithm", { exact: true }).selectOption("qpso_hybrid");
  await page.getByLabel("Iterations (updates)").fill("15");
  await page.getByLabel(/^Seed/).fill("4");
  await page.getByRole("button", { name: "Launch run" }).click();
  await expect(page.getByRole("region", { name: "Active run" })).toContainText("COMPLETED");
  await page.getByRole("region", { name: "Best solution" }).getByRole("button").first().click();
  await page.screenshot({ path: "test-results/screens/command-center.png" });

  // Simulation mid-way, with a slowdown incident on a road one vehicle still has to drive.
  const simulate = page.getByRole("button", { name: /Simulate the active run/ });
  await expect(simulate).toBeEnabled();
  await simulate.click();
  const panel = page.getByRole("region", { name: "Simulation" });
  for (let i = 0; i < 12; i++) await panel.getByRole("button", { name: "Step" }).click();
  await expect(panel).toContainText("0:06.0");
  const simId = await page.evaluate(
    () => JSON.parse(localStorage.getItem("trafiqon.workspace.v2")!).state.simulationId as string,
  );
  const sim = await (await request.get(api(`/simulations/${simId}`))).json();
  const ahead = sim.vehicles.find(
    (v: { remaining_edge_ids: string[] }) => v.remaining_edge_ids.length > 3,
  ).remaining_edge_ids[2];
  await page.locator(`[data-edge-id="${ahead}"] .road-edge-hit`).click({ force: true });
  await page.getByRole("button", { name: "Incident: close road" }).click();
  await panel.getByRole("button", { name: "Replan" }).click();
  await expect(panel.getByLabel("Last replan")).toBeVisible();
  await page.waitForTimeout(500); // let the 400 ms marker transition settle for the capture
  await page.screenshot({ path: "test-results/screens/simulation.png" });
  await panel.getByRole("button", { name: "Close simulation" }).click();

  await page
    .getByRole("navigation", { name: "Workspaces" })
    .getByRole("link", { name: "Algorithm Lab" })
    .click();
  await expect(
    page
      .getByRole("img", { name: /Best feasible objective/ })
      .locator("path")
      .first(),
  ).toBeAttached();
  await page.screenshot({ path: "test-results/screens/algorithm-lab.png" });

  await page
    .getByRole("navigation", { name: "Workspaces" })
    .getByRole("link", { name: "Scenario Studio" })
    .click();
  await page.getByLabel("Load a saved scenario").selectOption({ label: s.name });
  await page.locator('[data-edge-id="n2_2->n2_3"] .road-edge-hit').click({ force: true });
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText(/Valid\./)).toBeVisible();
  await page.screenshot({ path: "test-results/screens/scenario-studio.png" });

  await page
    .getByRole("navigation", { name: "Workspaces" })
    .getByRole("link", { name: "Experiment Explorer" })
    .click();
  await expect(page.getByRole("heading", { name: "Experiment Explorer" })).toBeVisible();
  await page.getByLabel("Scenario", { exact: true }).selectOption({ label: s.name });
  await page.getByRole("checkbox").first().check();
  await expect(page.getByRole("table", { name: "Run comparison" })).toBeVisible();
  await expect(
    page
      .getByRole("img", { name: /compared runs/ })
      .locator("path")
      .first(),
  ).toBeAttached();
  await page.screenshot({ path: "test-results/screens/experiments.png", fullPage: true });
});
