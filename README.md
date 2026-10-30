<div align="center">

<img src="assets/banner.svg" alt="TRAFIQON — transportation optimization and simulation workbench" width="100%"/>

<br/>

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-Web-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![OR-Tools](https://img.shields.io/badge/OR--Tools-reference-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://developers.google.com/optimization)
[![Docker](https://img.shields.io/badge/Docker-Compose_v2-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)

<br/>

**[⚡ Quick start](#-quick-start)** &nbsp;•&nbsp;
**[✨ Features](#-what-it-does)** &nbsp;•&nbsp;
**[🏗 Architecture](#-architecture)** &nbsp;•&nbsp;
**[🧪 Tests](#-tests-and-checks)** &nbsp;•&nbsp;
**[📚 Docs](#-documentation)** &nbsp;•&nbsp;
**[⚠️ Limitations](#%EF%B8%8F-limitations)**

</div>

<br/>

> **TRAFIQON** is a workbench for the **directed, capacity-constrained vehicle-routing problem (CVRP) on a road graph**.
> It supports dynamic traffic, road incidents and replanning, and compares three solvers under **one shared evaluator**.

<table align="center">
<tr>
<td align="center" width="33%">
<h3>🧮 OR-Tools</h3>
<sub>Reference solver</sub>
</td>
<td align="center" width="33%">
<h3>🔥 Simulated Annealing</h3>
<sub>Classical metaheuristic</sub>
</td>
<td align="center" width="33%">
<h3>🌀 QPSO-inspired hybrid</h3>
<sub>Classical, quantum-<i>inspired</i> sampling</sub>
</td>
</tr>
</table>

> [!IMPORTANT]
> **Scope, stated honestly**
> - **Not a general solution:** this is not traffic-signal control, traffic assignment or general fleet dispatch.
> - **Synthetic data:** the built-in networks are synthetic grids, not real geography.
> - **"Quantum-inspired" is classical:** it describes the sampling rule of a classical algorithm. Nothing runs on quantum hardware and no speedup is claimed. The hybrid is documented as *QPSO-inspired*, not canonical QPSO.

---

## ✨ What it does

Click a card to expand it.

<details open>
<summary><b>🎛 Command Center</b> — launch, watch, simulate</summary>
<br/>

- Load or import a scenario, launch a run, and watch live progress (**SSE**).
- Cancel a run, inspect its best routes on the map, and compare it with another run.
- Simulate the routes: step or run the clock, close or slow roads, and replan.

</details>

<details>
<summary><b>🔬 Algorithm Lab</b> — every knob, nothing hidden</summary>
<br/>

- Every algorithm parameter, with its description and limits, published by the backend.
- Convergence chart, execution statistics, diagnostics, and feasibility checks.

</details>

<details>
<summary><b>🗺 Scenario Studio</b> — build the road network</summary>
<br/>

- Edit nodes, one-way roads, travel times, closures, depots, customers, demand and the fleet.
- Validate on the server, then save as an **immutable version**.

</details>

<details>
<summary><b>📊 Experiment Explorer</b> — compare, benchmark, export</summary>
<br/>

- Filter run history and compare runs side by side.
- Benchmark suites (algorithms × seeds) with statistics and seed-level charts.
- CSV/JSON export with reproducibility metadata.

</details>

### 🛡 Honest by design

| Principle | What it means |
|---|---|
| **One evaluator** | Every displayed objective comes from one shared evaluator. |
| **No fake costs** | Unreachable legs are reported as infeasible, never given a large cost. |
| **Isolated execution** | Runs execute in a separate worker process. |
| **No fabrication** | Nothing shown is fabricated: measured, derived and simulated quantities are labelled. |

---

## 🏗 Architecture

<div align="center">
<img src="assets/architecture.svg" alt="Trafiqon architecture: browser, Next.js web, FastAPI, PostgreSQL, worker and core library" width="100%"/>
</div>

<details>
<summary>Plain-text version</summary>

```
 browser ── Next.js (web :3000) ──HTTP/SSE──▶ FastAPI (api :8000) ──SQL──▶ PostgreSQL
                                                     ▲                         ▲
                                                     │ core (pure Python)      │ SKIP LOCKED queue
                                                     │ domain · routing ·      │
                                                     │ optimization ·          │
                                                     │ simulation · experiments│
                                                     ▼                         │
                                              worker process(es) ─────────────┘
```

</details>

See [`docs/architecture.md`](docs/architecture.md). The job queue is the `optimization_runs` table, claimed with `FOR UPDATE SKIP LOCKED`; Celery + Redis is deferred (STATUS.md, D1).

---

## ⚡ Quick start

### 🐳 Docker (recommended)

Requires Docker with Compose v2.

```bash
git clone https://github.com/harish05-q/Trafiqon.git
cd Trafiqon
docker compose up --build
```

Then open **http://localhost:3000**. On startup:

```mermaid
flowchart LR
    A([docker compose up]) --> B[migrate<br/>Alembic on empty DB]
    B -->|exits| C[api]
    B -->|exits| D[worker]
    B -->|exits| E[web]
    E --> F([localhost:3000])
    style A fill:#6366f1,color:#fff,stroke:none
    style F fill:#22d3ee,color:#000,stroke:none
```

> [!TIP]
> **Your first optimization:** in the Command Center, import **"Urban Grid"**, then press **Launch run**.

<details>
<summary>🔧 Custom ports</summary>
<br/>

The browser calls the API directly, so set its public URL too:

```bash
API_PORT=8200 WEB_PORT=3200 PUBLIC_API_URL=http://localhost:8200 PUBLIC_WEB_URL=http://localhost:3200 docker compose up --build
```

</details>

> [!NOTE]
> This local stack has no password and publishes the database port. To put TRAFIQON on the internet (one AWS EC2 VM on Free plan credits, HTTPS, password, same-origin API), use the production override described in [`docs/deployment.md`](docs/deployment.md).

### 💻 Local development

<details>
<summary><b>Prerequisites and commands</b></summary>
<br/>

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 22 and npm
- Docker, for PostgreSQL

```bash
docker compose up -d db                       # PostgreSQL 18 on :5432
cd backend && uv sync
export TRAFIQON_DATABASE_URL=postgresql+psycopg://trafiqon:trafiqon@localhost:5432/trafiqon
uv run alembic upgrade head                   # migrations from a clean database
uv run uvicorn trafiqon.api.app:app --port 8000      # API   (terminal 1)
uv run python -m trafiqon.worker.main                # worker (terminal 2)
cd ../frontend && npm ci && npm run dev              # web on :3000 (terminal 3)
```

On Windows PowerShell, set the variable with `$env:TRAFIQON_DATABASE_URL = "..."`. Copy `.env.example` for all settings.

</details>

---

## 🧪 Tests and checks

<details>
<summary><b>Run everything</b></summary>
<br/>

```bash
cd backend  && uv run pytest                                   # unit + integration (real PostgreSQL)
cd backend  && uv run ruff check . && uv run ruff format --check .
cd frontend && npm test                                        # Vitest
cd frontend && npm run lint && npm run build                   # ESLint + Prettier, production build
cd frontend && npx playwright install chromium && npx playwright test   # E2E workflows 1-6 + a11y
```

</details>

| Suite | Notes |
|---|---|
| **Integration tests** | Use `trafiqon_test`. It is created and migrated automatically, and the tests are skipped and reported as **NOT RUN** if PostgreSQL is unreachable. |
| **Playwright** | Starts its own stack: API on :8100, a real worker, and a production build on :3100, against a fresh `trafiqon_e2e` database. |
| **CI** | `.github/workflows/ci.yml` runs all of the above. |

---

## ⚙️ Configuration

All settings come from environment variables; see [`.env.example`](.env.example).

| Area | Setting |
|---|---|
| 🗄 **Database** | `TRAFIQON_DATABASE_URL`. Without it the API still serves the built-in scenarios and shortest paths, and answers `503` for the rest. |
| 🌐 **CORS** | `TRAFIQON_CORS_ORIGINS` |
| ⏱ **Worker timing** | heartbeat, stale-run timeout, maximum attempts |
| 🚦 **Request limits** | `TRAFIQON_LIMIT_*` |
| 🖥 **Frontend** | `NEXT_PUBLIC_API_BASE_URL`, inlined at build time |

---

## 🩺 Troubleshooting

<details>
<summary><code>API: unreachable</code> in the top bar</summary>
<br/>

The web app cannot reach `NEXT_PUBLIC_API_BASE_URL`. Check that the API is running and that its URL and port match what the web build was given.

</details>

<details>
<summary>CORS errors in the browser console</summary>
<br/>

Add the web origin to `TRAFIQON_CORS_ORIGINS`.

</details>

<details>
<summary><code>DB: unavailable</code></summary>
<br/>

Start PostgreSQL (`docker compose up -d db`) and check `TRAFIQON_DATABASE_URL`. `GET /api/v1/ready` returns `503` until the database is reachable.

</details>

<details>
<summary>Runs stay <code>QUEUED</code></summary>
<br/>

No worker is running. Start one with `python -m trafiqon.worker.main`.

</details>

<details>
<summary>Simulation panel says the previous session is gone</summary>
<br/>

Simulation sessions live in the API's memory and are lost when it restarts (D27). Start a new one.

</details>

<details>
<summary>Docker errors mentioning <code>dockerDesktopLinuxEngine</code></summary>
<br/>

Docker Desktop is not running.

</details>

<details>
<summary>Node tools fail to connect to <code>localhost</code> but <code>127.0.0.1</code> works</summary>
<br/>

Node may resolve `localhost` to IPv6 `::1` while uvicorn listens on IPv4. The E2E config uses `127.0.0.1`.

</details>

---

## 📚 Documentation

| Document | Contents |
|---|---|
| 📐 [`docs/mathematical_model.md`](docs/mathematical_model.md) | Graph, CVRP, objective, constraints, evaluator |
| 🧠 [`docs/algorithms.md`](docs/algorithms.md) | Shortest paths, OR-Tools, SA, the QPSO-inspired formulation, complexity, limitations |
| 📈 [`docs/benchmark_methodology.md`](docs/benchmark_methodology.md) | Budgets, seeds, statistics, gap reference, exports |
| 🚦 [`docs/simulation.md`](docs/simulation.md) | Clock, vehicle state, incidents, replanning |
| 🔌 [`docs/api_contracts.md`](docs/api_contracts.md) | Endpoints, errors, SSE events, run lifecycle |
| 🏗 [`docs/architecture.md`](docs/architecture.md) | Components, data flow, infrastructure decisions |
| 🚀 [`docs/deployment.md`](docs/deployment.md) | Public deployment on AWS EC2 (`t3.small`, Free plan credits): Caddy HTTPS + password, budgets, backups, troubleshooting |
| 🎤 [`docs/interview_guide.md`](docs/interview_guide.md) | Decisions, trade-offs, failure modes, likely questions |
| 📝 [`STATUS.md`](STATUS.md) | Milestones, decisions (D1–D38), commands actually run, known defects |

---

## ⚠️ Limitations

> [!WARNING]
> These are known and documented, not hidden.

- The benchmark fixtures are small synthetic grids, plus one 30-customer experimental grid.
- Gaps are measured against the **best observed result**, not a proven optimum.
- There is **no exact or lower-bound method**.
- Simulation sessions are in-memory, for a single API process.
- There is no authentication; `owner_id` columns mark where it will plug in.
- See [STATUS.md](STATUS.md), "Known defects and open items".

<br/>

<div align="center">

<sub>Built with care for honest, reproducible routing experiments. If Trafiqon is useful to you, a ⭐ is appreciated.</sub>

</div>
