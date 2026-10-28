// SPEC_FULL 16 end-to-end workflow 6: export an experiment and verify that the exported
// metadata corresponds to the stored results.
import fs from "node:fs";

import { expect, test } from "@playwright/test";

import { API_URL } from "./stack";

const api = (p: string) => `${API_URL}/api/v1${p}`;

test("6: export an experiment and verify it against the stored results", async ({
  page,
  request,
}) => {
  const name = `E2E export ${Date.now()}`;
  const scenario = await (
    await request.post(api("/scenarios"), { data: { name, builtin_id: "incident_response" } })
  ).json();
  const versionId = scenario.current_version_id as string;
  const suite = await (
    await request.post(api("/suites"), {
      data: {
        name,
        scenario_version_id: versionId,
        specs: [
          { algorithm_id: "simulated_annealing", config: { max_iterations: 2000 } },
          { algorithm_id: "qpso_hybrid", config: { swarm_size: 6, iterations: 4 } },
        ],
        seeds: [3, 7],
        budget_policy: "SA 2000 moves; QPSO 6x4 particles",
      },
    })
  ).json();
  await expect
    .poll(
      async () =>
        (await (await request.get(api(`/suites/${suite.id}`))).json()).status_counts.COMPLETED ?? 0,
      {
        timeout: 60_000,
      },
    )
    .toBe(4);

  // Stored ground truth from the API.
  const version = await (await request.get(api(`/scenario-versions/${versionId}`))).json();
  const stored = new Map<string, { objective: number; seed: number; spec: string }>();
  for (const runId of suite.run_ids as string[]) {
    const run = await (await request.get(api(`/runs/${runId}`))).json();
    const result = await (await request.get(api(`/runs/${runId}/result`))).json();
    stored.set(`${run.suite_spec}#${run.repetition}`, {
      objective: result.objective,
      seed: result.seed,
      spec: run.suite_spec,
    });
  }

  await page.goto("/experiments");
  await page.getByRole("tab", { name: "Benchmark suites" }).click();
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.getByRole("table", { name: "Suite statistics" })).toContainText("2/2");
  await expect(
    page
      .getByRole("img", { name: /Objective of each completed run/ })
      .locator("path")
      .first(),
  ).toBeAttached();

  // JSON export through the UI.
  const [jsonDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: /Export JSON/ }).click(),
  ]);
  expect(jsonDownload.suggestedFilename()).toBe(`suite-${suite.id}.json`);
  const exported = JSON.parse(fs.readFileSync((await jsonDownload.path())!, "utf8"));
  expect(exported.metadata.suite_id).toBe(suite.id);
  expect(exported.metadata.scenario_version_id).toBe(versionId);
  expect(exported.metadata.scenario_fingerprint).toBe(version.fingerprint);
  expect(exported.metadata.seeds).toEqual([3, 7]);
  expect(exported.metadata.budget_policy).toBe("SA 2000 moves; QPSO 6x4 particles");
  expect(exported.metadata.evaluator_version).toBe("1");
  expect(exported.metadata.software[0].ortools).toBeTruthy();
  expect(exported.metadata.specs.map((s: { label: string }) => s.label)).toEqual([
    "simulated_annealing",
    "qpso_hybrid",
  ]);
  expect(exported.quantity_kinds.elapsed_s).toBe("measured");
  expect(exported.runs).toHaveLength(4);
  for (const r of exported.runs) {
    const truth = stored.get(`${r.spec}#${r.repetition}`)!;
    expect(r.objective).toBe(truth.objective);
    expect(r.seed).toBe(truth.seed);
  }
  const best = Math.min(...[...stored.values()].map((s) => s.objective));
  expect(exported.reference).toMatchObject({ kind: "best_observed_heuristic", objective: best });

  // CSV export has the same rows.
  const [csvDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: /Export CSV/ }).click(),
  ]);
  const lines = fs
    .readFileSync((await csvDownload.path())!, "utf8")
    .trim()
    .split("\n");
  const header = lines[0].split(",");
  const objIdx = header.indexOf("objective");
  expect(lines).toHaveLength(5);
  expect(
    lines
      .slice(1)
      .map((l) => Number(l.split(",")[objIdx]))
      .sort(),
  ).toEqual([...stored.values()].map((s) => s.objective).sort());
});
