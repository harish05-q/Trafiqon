# Deploying TRAFIQON for free

This guide puts the whole stack (PostgreSQL, migrations, API, worker, web app) on one free cloud
VM behind Caddy, with HTTPS and a password. Total cost: 0, if you stay within the provider's free
limits.

## Contents
1. [Why a VM, and which one](#1-why-a-vm-and-which-one)
2. [What gets deployed](#2-what-gets-deployed)
3. [Create the Oracle Cloud VM](#3-create-the-oracle-cloud-vm)
4. [Open the firewall](#4-open-the-firewall-two-places)
5. [Get a free domain](#5-get-a-free-domain-duckdns)
6. [Install Docker](#6-install-docker-on-the-vm)
7. [Configure and start TRAFIQON](#7-configure-and-start-trafiqon)
8. [Check it works](#8-check-that-it-works)
9. [Day-2 operations](#9-day-2-operations)
10. [Troubleshooting](#10-troubleshooting)
11. [Alternative: your own computer + Cloudflare quick tunnel](#11-alternative-your-own-computer--cloudflare-quick-tunnel)
12. [What was verified](#12-what-was-verified)

---

## 1. Why a VM, and which one

TRAFIQON needs four things running **all the time**: PostgreSQL, the API, a **separate worker
process** that executes runs, and the web app. The worker must never sleep, otherwise runs stay
`QUEUED`. The API also keeps simulation sessions in memory (STATUS.md D27), so it must be a
single long-lived process.

That rules out most "free tier" platforms:

| Option | Problem for TRAFIQON |
|---|---|
| Render free | Free web services sleep when idle; free background workers are not offered; free Postgres expires. |
| Vercel / Netlify | Fine for the web app only; they cannot run the Python worker or Postgres. |
| Neon / Supabase free Postgres | Database only; you still need somewhere for the API and worker. |
| Fly.io, Railway | No permanent free tier for new accounts (trial credit only). |
| Google Cloud e2-micro (free) | 1 GB RAM: too little for OR-Tools + Postgres + Next.js. |
| **Oracle Cloud "Always Free" Ampere A1** | **Up to 4 ARM cores and 24 GB RAM, free with no time limit. Runs the full stack unchanged.** |

Free-tier terms change. Check the provider's current Always Free page before you start. The
recommendation here reflects their published terms at the time of writing.

**Known Oracle caveats** (plan for them, then they are not problems):
- Sign-up needs a credit/debit card for identity verification. Always Free resources are not charged.
- You choose a **home region** once, at sign-up; Always Free compute is created there. Pick one
  near you.
- A1 capacity is sometimes exhausted ("Out of capacity"). Retry later, try another availability
  domain, or use a smaller shape (section 10).
- Oracle may **reclaim idle Always Free instances** (very low CPU, network and memory use over 7
  days). An instance that is actually used is fine. Upgrading the account to Pay As You Go removes
  the idle reclamation rule while Always Free resources stay free; only do that if you understand
  that resources *beyond* the free limits would then be billed.

## 2. What gets deployed

```
Internet ──443/80──> Caddy (HTTPS, password)
                        ├── /api/*  ──> api :8000 (FastAPI)  ──┐
                        └── /*      ──> web :3000 (Next.js)    ├──> db (PostgreSQL 18, private)
                                         worker (runs jobs) ───┘
```

Files used (all in the repo):
- `docker-compose.yml`: the stack itself.
- `docker-compose.prod.yml`: the production override. Only Caddy is reachable from outside; the
  database password comes from your env file; the web app calls the API on its own address;
  container logs are capped at 30 MB per service.
- `deploy/Caddyfile`: routing, automatic HTTPS (Let's Encrypt), password prompt, SSE pass-through.
- `deploy/.env.example`: the settings you fill in.

Why the password: TRAFIQON has no user accounts. Without the Caddy password, anyone who finds the
URL can create scenarios and queue optimization runs on your VM.

## 3. Create the Oracle Cloud VM

1. Sign up at the Oracle Cloud website (Free Tier). Choose your home region carefully.
2. In the console: **Compute → Instances → Create instance**.
3. **Image:** click *Change image* → **Canonical Ubuntu 24.04** (the aarch64 build is selected
   automatically for Ampere).
4. **Shape:** *Change shape* → **Ampere** → `VM.Standard.A1.Flex`. Set **2 OCPUs and 12 GB**
   (enough; leaves free headroom) or up to 4 OCPUs / 24 GB.
5. **Networking:** keep the default new VCN with a public subnet and **Assign a public IPv4
   address** = yes.
6. **SSH keys:** *Generate a key pair for me* and download the private key, or paste your own
   public key (`ssh-keygen -t ed25519` creates one).
7. **Boot volume:** the default (about 47 GB) is fine; Always Free includes up to 200 GB total.
8. Click **Create**, wait for *Running*, and copy the **Public IP address**.

Connect (Windows PowerShell, macOS or Linux):

```bash
ssh -i path/to/private.key ubuntu@YOUR_PUBLIC_IP
```

If SSH refuses the key on Linux/macOS, run `chmod 600 path/to/private.key` first.

## 4. Open the firewall (two places)

Oracle blocks web traffic in **two** places. Both must allow ports 80 and 443, or Let's Encrypt
cannot issue the certificate.

**a) Oracle network (Security List).** Instance page → *Primary VNIC* → the **Subnet** → *Security
Lists* → *Default Security List* → **Add Ingress Rules**:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |
| `0.0.0.0/0` | UDP | `443` (optional, HTTP/3) |

**b) The VM's own firewall.** Oracle's Ubuntu images ship iptables rules that reject everything
except SSH. On the VM:

```bash
sudo iptables -I INPUT 1 -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT
sudo iptables -I INPUT 1 -p udp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Do **not** run `ufw enable` on these images; it conflicts with Oracle's rules and can lock you out
of SSH.

## 5. Get a free domain (DuckDNS)

Let's Encrypt needs a domain name, not a bare IP.

1. Go to the DuckDNS website and sign in (GitHub, Google, etc.).
2. Add a subdomain, e.g. `trafiqon-yourname` → you get `trafiqon-yourname.duckdns.org`.
3. Put your VM's **public IP** in the *current ip* box and click *update ip*.
4. Check from your own computer: `nslookup trafiqon-yourname.duckdns.org` should print that IP.

If you already own a domain, add an `A` record pointing to the VM instead.

## 6. Install Docker on the VM

Docker's official apt repository (current Docker Engine and the Compose plugin):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Log out and SSH in again (so the `docker` group applies), then check:

```bash
docker run --rm hello-world
docker compose version
```

`docker compose version` must be **2.24 or newer** (the override uses `!reset`). Docker starts on
boot by default, and every TRAFIQON service has `restart: unless-stopped`, so the app comes back
after a reboot.

## 7. Configure and start TRAFIQON

```bash
git clone https://github.com/harish05-q/Trafiqon.git trafiqon
cd trafiqon
cp deploy/.env.example deploy/.env
```

Generate the two secrets:

```bash
openssl rand -hex 24
docker run --rm caddy:2.10-alpine caddy hash-password --plaintext 'choose-a-login-password'
```

Edit `deploy/.env` (`nano deploy/.env`):

```ini
SITE_ADDRESS=trafiqon-yourname.duckdns.org
PUBLIC_WEB_URL=https://trafiqon-yourname.duckdns.org
POSTGRES_PASSWORD=<the openssl output>
BASIC_AUTH_USER=trafiqon
BASIC_AUTH_HASH='<the hash-password output, inside single quotes>'
```

Rules that prevent the usual failures:
- `POSTGRES_PASSWORD`: letters and digits only (it is embedded in a database URL). The hex output
  is safe.
- `BASIC_AUTH_HASH`: keep the **single quotes**. The hash contains `$`, which Compose would
  otherwise try to expand.
- `SITE_ADDRESS`: the bare domain, no `https://`, no trailing slash.
- The DB password only takes effect when the database volume is **first** created. To change it
  later, change it inside Postgres too (or start over with `down -v`, which deletes all data).

Make a short alias (add it to `~/.bashrc` to keep it):

```bash
alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file deploy/.env'
```

Build and start (the first build compiles the web app and downloads dependencies; it takes a few
minutes):

```bash
dc up -d --build
dc ps -a
```

Expected: `db`, `api`, `web` **healthy**, `worker` and `caddy` **running**, `migrate`
**exited (0)**. `migrate` is a one-shot job that applies database migrations and then exits;
that is correct. (Do not add `--wait`: it reports an error because the worker deliberately has no
healthcheck.)

## 8. Check that it works

1. Open `https://trafiqon-yourname.duckdns.org` in a browser. You get a login prompt; use
   `BASIC_AUTH_USER` and the password you hashed.
2. The top bar should show **API: online · DB: ok**.
3. Command Center → import a built-in scenario → launch a run. It should go QUEUED → RUNNING →
   COMPLETED with live progress, and still be there after a page reload.

From a terminal:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://trafiqon-yourname.duckdns.org/          # 401 (password required)
curl -s -u trafiqon:YOUR_PASSWORD https://trafiqon-yourname.duckdns.org/api/v1/ready     # {"ready":true,...}
```

## 9. Day-2 operations

All commands run in the `trafiqon` folder with the `dc` alias.

| Task | Command |
|---|---|
| Status | `dc ps -a` |
| Logs (follow) | `dc logs -f --tail 100 api worker` |
| Restart one service | `dc restart worker` |
| Stop everything (keeps data) | `dc down` |
| Start again | `dc up -d` |
| Update to the latest code | `git pull && dc up -d --build` (migrations run automatically) |
| Free disk from old images | `docker image prune -f` |

**Backups.** The database lives in a Docker volume on the VM's boot disk. Take a dump and copy it
off the VM:

```bash
mkdir -p ~/backups
dc exec -T db pg_dump -U trafiqon -d trafiqon --format=custom > ~/backups/trafiqon-$(date +%F).dump
```

Nightly at 03:00, keeping 14 days (`crontab -e`, one line; replace the path):

```
0 3 * * * cd /home/ubuntu/trafiqon && docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file deploy/.env exec -T db pg_dump -U trafiqon -d trafiqon --format=custom > /home/ubuntu/backups/trafiqon-$(date +\%F).dump && find /home/ubuntu/backups -name '*.dump' -mtime +14 -delete
```

Copy a backup to your computer: `scp -i key ubuntu@YOUR_PUBLIC_IP:backups/trafiqon-DATE.dump .`

**Restore** into the running stack (replaces the current data):

```bash
dc stop api worker
dc exec -T db pg_restore -U trafiqon -d trafiqon --clean --if-exists --no-owner < ~/backups/trafiqon-DATE.dump
dc start api worker
```

**Limits.** To protect the free VM, lower the request limits in `deploy/.env`, for example
`TRAFIQON_LIMIT_MAX_QUEUED_RUNS=50` and `TRAFIQON_LIMIT_MAX_TIME_LIMIT_S=60` (all names in
`docs/api_contracts.md`), then pass them through by adding them to the `api` and `worker`
`environment:` in `docker-compose.prod.yml`, and run `dc up -d`.

**What a restart loses.** Runs, scenarios, results and suites are in Postgres and survive
restarts. Live **simulation sessions** are in API memory (D27) and end when the `api` container
restarts; the UI says so. Queued runs survive; a run that was mid-execution when the worker
stopped is picked up again by stale-run recovery.

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Out of capacity for shape VM.Standard.A1.Flex" | Oracle has no free A1 capacity at that moment. Try another availability domain, a smaller shape (1 OCPU / 6 GB should be enough, with slower builds and runs; not measured), or retry later. |
| Browser times out; no certificate; `caddy` logs mention `timeout during connect` or `challenge failed` | Ports 80/443 are blocked. Recheck **both** firewall steps (section 4) and that DuckDNS points to the current public IP. Then `dc restart caddy`. |
| Certificate errors after many retries | Let's Encrypt rate limits after repeated failures. Fix the cause, wait an hour, `dc restart caddy`. Do not delete the `caddy_data` volume repeatedly. |
| `required variable POSTGRES_PASSWORD is missing` (or SITE_ADDRESS, BASIC_AUTH_*) | `deploy/.env` is missing that line, or you forgot `--env-file deploy/.env` (use the `dc` alias). |
| Login prompt never accepts the password | The hash lost its `$` signs: put it in single quotes in `deploy/.env`, then `dc up -d`. Check with `dc exec caddy printenv BASIC_AUTH_HASH` (must start with `$2a$`). |
| `migrate` exited with code 1; api never starts | Database password mismatch, usually because `POSTGRES_PASSWORD` was changed after the volume was created. See section 7. `dc logs migrate` shows the exact error. |
| Top bar says **API: offline** | `dc ps -a`; `dc logs api`. The page and API must be on the same address (the prod override builds the web app for that). If you changed the override, rebuild: `dc up -d --build web`. |
| Runs stay QUEUED | The worker is not running: `dc logs worker`, `dc restart worker`. |
| `!reset` / "unknown tag" error | Compose is older than 2.24. Install the current `docker-compose-plugin` (section 6). |
| IP changed after stopping the instance | Update the IP in DuckDNS. (To avoid it, keep the instance running, or use a reserved public IP if your account allows one.) |
| Disk filling up | `docker system df`; `docker image prune -f`; delete old backups. Logs are already capped. |
| Instance stopped by Oracle | Idle reclamation (section 1). Start it again from the console; data on the boot volume is kept. |

## 11. Alternative: your own computer + Cloudflare quick tunnel

For a short demo without any cloud account: run the production stack on your own machine and
expose it through a Cloudflare *quick tunnel* (free, no account, temporary random URL). It is only
reachable while your computer is on.

1. In `deploy/.env`: `SITE_ADDRESS=:80`, `HTTP_PORT=8088`, `HTTPS_PORT=8443`,
   `PUBLIC_WEB_URL=http://localhost:8088`, plus the password and hash as in section 7.
2. `dc up -d --build`, then open `http://localhost:8088` to check it locally.
3. Install `cloudflared` from Cloudflare's downloads page and run
   `cloudflared tunnel --url http://localhost:8088`. It prints a `https://….trycloudflare.com` URL
   that serves the app over HTTPS (Cloudflare terminates TLS; Caddy serves plain HTTP behind it).

The local half of this (steps 1–2) is verified; the Cloudflare tunnel itself was not tested
(section 12).

## 12. What was verified

Verified on 2026-10-29 on the development machine (Windows 11, Docker Desktop, Compose 2.39),
running exactly `docker-compose.yml` + `docker-compose.prod.yml` + `deploy/Caddyfile` with
`SITE_ADDRESS=:80` on host port 8088:
- Only Caddy publishes ports; Postgres, API and web are unreachable from the host.
- Without the password: page and API both return 401; a wrong password gets 401; with it, 200.
- A run submitted through Caddy is executed by the worker container (COMPLETED, objective 73.8);
  its Server-Sent Events (queued, started, progress, completed, end) arrive through the proxy.
- In a real browser (Playwright, HTTP credentials): every request goes to the single site address
  (no direct API calls); the Command Center imports a scenario, runs SA to COMPLETED with live
  events, and the run is still there after a reload. The built web bundle contains no
  `localhost:8000`.
- `down` then `up -d` keeps all runs. `pg_dump` + `pg_restore` round-trip into a fresh database
  gives identical run and event counts, and the in-place restore in section 9 (stop api/worker,
  `pg_restore --clean`, start) exits 0 with the API ready and the runs present.
- The backend image builds for `linux/arm64` (emulated) from the locked dependencies, and OR-Tools,
  NumPy, psycopg and the API import on it (see STATUS.md for the exact output).

**Not verified here:** an actual Oracle Cloud VM, Let's Encrypt issuance on a public domain
(Caddy's automatic HTTPS, used as documented), DuckDNS, and the Cloudflare tunnel. These steps
follow the providers' documented procedures; section 10 covers the failures people hit most often.
