// Shared settings for the end-to-end stack: a dedicated database, API on 8100, web on 3100.
import path from "node:path";

export const DB_URL =
  process.env.TRAFIQON_E2E_DATABASE_URL ??
  "postgresql+psycopg://trafiqon:trafiqon@localhost:5432/trafiqon_e2e";
export const API_PORT = 8100;
export const WEB_PORT = 3100;
export const API_URL = `http://127.0.0.1:${API_PORT}`; // explicit IPv4: uvicorn binds 127.0.0.1
export const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;
export const BACKEND_DIR = path.resolve(__dirname, "..", "..", "backend");

/** Environment for the API and worker processes. Short timings keep the tests fast. */
export const BACKEND_ENV: Record<string, string> = {
  TRAFIQON_DATABASE_URL: DB_URL,
  TRAFIQON_CORS_ORIGINS: WEB_URL,
  TRAFIQON_HEARTBEAT_INTERVAL_S: "0.2",
  TRAFIQON_PROGRESS_EVENT_MIN_INTERVAL_S: "0.2",
  TRAFIQON_WORKER_POLL_INTERVAL_S: "0.2",
};
