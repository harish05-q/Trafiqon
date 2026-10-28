// Recreates the e2e database from clean via Alembic and starts a REAL worker process.
// The API and web servers are started by Playwright's `webServer` config.
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { BACKEND_DIR, BACKEND_ENV, DB_URL } from "./stack";

export const PID_FILE = path.join(__dirname, ".worker.pid");

export default async function globalSetup() {
  const out = execFileSync("uv", ["run", "python", path.join(__dirname, "reset_db.py"), DB_URL], {
    cwd: BACKEND_DIR,
    env: { ...process.env, ...BACKEND_ENV },
    encoding: "utf8",
    shell: process.platform === "win32",
  });
  process.stdout.write(out);
  const log = fs.openSync(path.join(__dirname, ".worker.log"), "w");
  const worker = spawn("uv", ["run", "python", "-m", "trafiqon.worker.main"], {
    cwd: BACKEND_DIR,
    env: { ...process.env, ...BACKEND_ENV },
    stdio: ["ignore", log, log],
    shell: process.platform === "win32",
    detached: process.platform !== "win32",
  });
  fs.writeFileSync(PID_FILE, String(worker.pid));
}
