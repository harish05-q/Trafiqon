import { defineConfig, devices } from "@playwright/test";

import { API_PORT, API_URL, BACKEND_DIR, BACKEND_ENV, WEB_PORT, WEB_URL } from "./e2e/stack";

/**
 * End-to-end workflows against the real stack: PostgreSQL (docker compose `db`), the FastAPI
 * app, a separate worker process and a production build of the web app.
 * Run: `npx playwright test` (needs `docker compose up -d db`).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    {
      command: `uv run uvicorn trafiqon.api.app:app --port ${API_PORT}`,
      cwd: BACKEND_DIR,
      env: BACKEND_ENV,
      // /health, not /ready: Playwright starts web servers BEFORE globalSetup creates the e2e
      // database, so readiness would wait forever. The pre-ping pool reconnects afterwards.
      url: `${API_URL}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run build && npx next start -p ${WEB_PORT}`,
      env: { NEXT_PUBLIC_API_BASE_URL: API_URL },
      url: WEB_URL + "/command-center",
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
