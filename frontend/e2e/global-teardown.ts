import { execFileSync } from "node:child_process";
import fs from "node:fs";

import { PID_FILE } from "./global-setup";

export default async function globalTeardown() {
  if (!fs.existsSync(PID_FILE)) return;
  const pid = Number(fs.readFileSync(PID_FILE, "utf8"));
  try {
    if (process.platform === "win32") {
      execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(-pid, "SIGTERM");
    }
  } catch {
    // already gone
  }
  fs.rmSync(PID_FILE, { force: true });
}
