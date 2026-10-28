// Accessibility audit: axe-core WCAG 2 A/AA rules on every workspace with real data loaded.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { API_URL } from "./stack";

const api = (p: string) => `${API_URL}/api/v1${p}`;

async function audit(page: Page, label: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // React Flow's attribution link is third-party chrome outside our control.
    .exclude(".react-flow__attribution")
    .analyze();
  const summary = results.violations.map(
    (v) => `${label}: ${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes[0]?.target.join(" ")}`,
  );
  expect(summary, summary.join("\n")).toEqual([]);
}

test("workspaces have no WCAG 2 A/AA violations", async ({ page, request }) => {
  const name = `A11y ${Date.now()}`;
  const s = await (
    await request.post(api("/scenarios"), { data: { name, builtin_id: "urban_grid" } })
  ).json();
  const run = await (
    await request.post(api("/runs"), {
      data: {
        scenario_version_id: s.current_version_id,
        algorithm_id: "simulated_annealing",
        config: { max_iterations: 2000 },
        seed: 1,
      },
    })
  ).json();
  await expect
    .poll(async () => (await (await request.get(api(`/runs/${run.id}`))).json()).status)
    .toBe("COMPLETED");

  await page.goto("/command-center");
  await page.getByRole("button", { name, exact: true }).click();
  await page
    .getByRole("region", { name: "Runs on this version" })
    .getByRole("button")
    .first()
    .click();
  await expect(page.getByRole("list", { name: "Vehicle routes" })).toBeVisible();
  await audit(page, "command-center (dark)");

  await page.getByRole("button", { name: /Simulate the active run/ }).click();
  await expect(page.getByRole("region", { name: "Simulation" })).toContainText("ready");
  await audit(page, "command-center simulation");

  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await audit(page, "command-center (light)");

  const nav = page.getByRole("navigation", { name: "Workspaces" });
  await nav.getByRole("link", { name: "Algorithm Lab" }).click();
  await expect(page.getByLabel("swarm_size")).toBeVisible();
  await audit(page, "algorithm-lab");

  await nav.getByRole("link", { name: "Scenario Studio" }).click();
  await page.getByLabel("Load a saved scenario").selectOption({ label: name });
  await expect(page.getByText(/saving creates a new version/)).toBeVisible();
  await audit(page, "scenario-studio");

  await nav.getByRole("link", { name: "Experiment Explorer" }).click();
  await page.getByLabel("Scenario", { exact: true }).selectOption({ label: name });
  await page.getByRole("checkbox").first().check();
  await expect(page.getByRole("table", { name: "Run comparison" })).toBeVisible();
  await audit(page, "experiments (light)");
});

test("keyboard: workspaces and main controls are reachable with Tab", async ({ page }) => {
  await page.goto("/command-center");
  const reached = new Set<string>();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    const label = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return el ? (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 60) : "";
    });
    reached.add(label);
  }
  for (const target of [
    "Command Center",
    "Algorithm Lab",
    "Scenario Studio",
    "Experiment Explorer",
  ]) {
    expect([...reached]).toContain(target);
  }
  expect([...reached].some((l) => /Switch to (light|dark) theme/.test(l))).toBe(true);
  // Focus is visible: the focused element shows either the token outline or a shadcn focus ring.
  const indicator = await page.evaluate(() => {
    const cs = getComputedStyle(document.activeElement!);
    return { outline: cs.outlineStyle, ring: cs.boxShadow };
  });
  expect(indicator.outline !== "none" || indicator.ring !== "none").toBe(true);
});
