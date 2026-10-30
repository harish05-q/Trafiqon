# Deploying TRAFIQON on AWS (Free plan credits)

This guide puts the whole stack (PostgreSQL, migrations, API, worker, web app) on **one EC2
virtual machine** behind Caddy, with HTTPS and a password, paid for by the AWS Free plan credits
on a new account. You use the AWS account you already have; on the Free plan AWS does not charge
you, usage is deducted from your credits.

Follow the sections in order. Every command is meant to be copied exactly; replace only the
values in `CAPITALS` or `<angle brackets>`.

## Contents
0. [Before you start: how the Free plan works](#0-before-you-start-how-the-free-plan-works)
1. [Protect your credits (do this first)](#1-protect-your-credits-do-this-first)
2. [Choose a region](#2-choose-a-region)
3. [Create an SSH key pair](#3-create-an-ssh-key-pair)
4. [Launch the EC2 instance](#4-launch-the-ec2-instance)
5. [Give it a fixed IP (Elastic IP)](#5-give-it-a-fixed-ip-elastic-ip)
6. [Connect to the instance](#6-connect-to-the-instance)
7. [Prepare the server (updates, swap)](#7-prepare-the-server-updates-swap)
8. [Get a free domain (DuckDNS)](#8-get-a-free-domain-duckdns)
9. [Install Docker](#9-install-docker)
10. [Put your code on GitHub](#10-put-your-code-on-github)
11. [Configure and start TRAFIQON](#11-configure-and-start-trafiqon)
12. [Check that it works](#12-check-that-it-works)
13. [Day-to-day operations](#13-day-to-day-operations)
14. [Saving credits](#14-saving-credits)
15. [Before the Free plan ends / shutting down](#15-before-the-free-plan-ends--shutting-down)
16. [Troubleshooting](#16-troubleshooting)
17. [Alternative: your own computer + Cloudflare quick tunnel](#17-alternative-your-own-computer--cloudflare-quick-tunnel)
18. [What was verified](#18-what-was-verified)

---

## 0. Before you start: how the Free plan works

Facts from AWS's Free Tier pages (checked 2026-10-30; check your own console, the numbers on
your account are what count):

- New accounts (created on or after 15 July 2025) get **USD 100 in credits at sign-up** and can
  earn **up to USD 100 more** by completing activities listed in the *Explore AWS* widget on the
  console home page (filter: *Earn AWS credits*).
- The **Free plan ends after 6 months or when the credits are used up, whichever comes first**.
  It does not turn into a paid account by itself: if you do not upgrade, **AWS closes the account**
  and you lose access to resources and data (AWS keeps them for 90 days, but you must upgrade to
  get them back). So: watch the credits, and take backups off the server (section 13).
- On the Free plan you can only launch **Free-tier-eligible instance types**. For new accounts
  these are `t3.micro`, `t3.small`, `t4g.micro`, `t4g.small`, `c7i-flex.large`, `m7i-flex.large`.
  The console marks them *Free tier eligible*.
- Everything you run costs credits: the instance per hour, the disk per GB-month, and the
  **public IPv4 address at USD 0.005/hour** (about USD 3.65/month, whether it is an Elastic IP or
  an auto-assigned one).

**Which instance: `t3.small`** (2 vCPU, 2 GiB RAM, x86).
- `t3.micro`/`t4g.micro` have 1 GiB, too tight for building the web app plus Postgres.
- `t3.small` fits. Measured on this stack: the whole running stack peaks at **about 313 MiB**
  while executing OR-Tools, SA and QPSO runs, and the web build peaks at **about 940 MiB**; with
  2 GiB of RAM and 2 GiB of swap there is ample headroom.
- `c7i-flex.large`/`m7i-flex.large` are faster but cost several times more per hour, so the
  credits would not last 6 months.
- `t4g.small` (ARM) is slightly cheaper and should also work (the backend image was built and
  tested for ARM), but the web image was not built for ARM; `t3.small` is the path that was
  tested end to end.

**Expected cost (estimate, not a quote).** At US East on-demand rates (t3.small about
USD 0.021/hour, gp3 disk about USD 0.08/GB-month, IPv4 USD 0.005/hour), running 24/7:

| Item | Per month (approx.) |
|---|---|
| t3.small, 730 hours | ~ USD 15.2 |
| Public IPv4 (Elastic IP), 730 hours | ~ USD 3.7 |
| 20 GiB gp3 disk | ~ USD 1.6 |
| Data transfer out (a demo's traffic) | usually < USD 1 |
| **Total** | **~ USD 20-21** |

So USD 100 lasts roughly **4.5-5 months** of 24/7 running; earning the extra USD 100 covers the
full 6 months. Prices differ slightly per region (for example Mumbai): check the
**AWS Pricing Calculator** for your region before relying on these numbers. Stopping the
instance when you are not using it saves most of the cost (section 14).

## 1. Protect your credits (do this first)

1. Sign in to the **AWS Management Console** as your account's root user (or an admin user).
2. Top search bar → **Billing and Cost Management**.
3. Left menu → **Credits**: note the **remaining amount** and the **expiration date**.
4. Left menu → **Free Tier**: note your **plan end date**. Write both dates down.
5. On the console home page, open the **Explore AWS** widget, filter **Earn AWS credits**, and
   complete the activities you can (one of them may be creating a budget, which you do next).
6. Create a budget alert so you know how fast credits are being used:
   1. **Billing and Cost Management → Budgets → Create budget**.
   2. Choose **Customize (advanced)** → **Cost budget** → Next.
   3. Name: `trafiqon-monthly`. Period: **Monthly**. Budget amount: **25** (USD).
   4. Open **Advanced options**: keep *Unblended costs*, and in the charge types make sure
      **"Credits" is not checked** (uncheck "Refunds" too). Then the budget tracks real usage
      instead of showing 0 because credits cancel it out.
   5. Add alert thresholds: **50 %** and **80 %** of budgeted amount, **Actual**, with your
      e-mail address. Optionally add one at **100 %, Forecasted**.
   6. Create the budget and confirm the e-mail subscription if AWS asks.

## 2. Choose a region

Top-right of the console, pick **one region close to your users** and keep using it for every
step below (instances, key pairs, Elastic IPs are per region). From India, **Asia Pacific
(Mumbai) `ap-south-1`** is the natural choice. If you later "lose" your instance, first check the
region selector.

## 3. Create an SSH key pair

1. Console search → **EC2** → left menu **Network & Security → Key Pairs** → **Create key pair**.
2. Name: `trafiqon-key`. Key pair type: **ED25519**. Private key file format: **.pem**.
3. **Create key pair**. The browser downloads `trafiqon-key.pem`. AWS never shows it again: keep
   it safe, and do not commit it to git.

**Windows** (PowerShell): move it and lock down its permissions, otherwise `ssh` refuses it with
"UNPROTECTED PRIVATE KEY FILE":

```powershell
mkdir $env:USERPROFILE\.ssh -Force
Move-Item $env:USERPROFILE\Downloads\trafiqon-key.pem $env:USERPROFILE\.ssh\trafiqon-key.pem
icacls "$env:USERPROFILE\.ssh\trafiqon-key.pem" /inheritance:r
icacls "$env:USERPROFILE\.ssh\trafiqon-key.pem" /grant:r "$($env:USERNAME):(R)"
```

**macOS / Linux:**

```bash
mkdir -p ~/.ssh && mv ~/Downloads/trafiqon-key.pem ~/.ssh/ && chmod 400 ~/.ssh/trafiqon-key.pem
```

## 4. Launch the EC2 instance

EC2 → **Instances → Launch instances**, then fill in the form from top to bottom:

1. **Name:** `trafiqon`.
2. **Application and OS Images (AMI):** **Ubuntu** → **Ubuntu Server 24.04 LTS (HVM), SSD Volume
   Type**, architecture **64-bit (x86)**. It is labelled *Free tier eligible*.
3. **Instance type:** **`t3.small`** (labelled *Free tier eligible*).
4. **Key pair (login):** `trafiqon-key`.
5. **Network settings → Edit:**
   - VPC: the default VPC. Subnet: *No preference*.
   - **Auto-assign public IP: Enable.**
   - Firewall (security groups): **Create security group**, name `trafiqon-sg`,
     description `TRAFIQON web and SSH`.
   - Inbound rules (use **Add security group rule** for each):

     | Type | Port | Source type | Why |
     |---|---|---|---|
     | SSH | 22 | **My IP** | Only your current IP can log in. |
     | HTTP | 80 | **Anywhere** (0.0.0.0/0) | Let's Encrypt certificate check and redirect to HTTPS. |
     | HTTPS | 443 | **Anywhere** (0.0.0.0/0) | The site. |

     Do **not** open 5432, 8000 or 3000; the production setup keeps those private.
6. **Configure storage:** **20 GiB**, volume type **gp3**. (The images take about 2.6 GB, plus
   build cache and the database; 20 GiB is comfortable.)
7. **Advanced details** (expand it), change only:
   - **Credit specification:** **Standard**. T3 instances default to *Unlimited*, where sustained
     high CPU is billed extra (USD 0.05 per vCPU-hour of surplus). *Standard* just slows the CPU
     down when its burst credits run out, which costs nothing extra. TRAFIQON is idle most of the
     time, so Standard is fine.
8. Right side **Summary:** check *1 instance*, `t3.small`, 20 GiB → **Launch instance**.
9. **View all instances**. Wait until *Instance state* = **Running** and *Status check* =
   **3/3 checks passed** (a few minutes).

If the launch fails with a message about the instance type not being eligible for the Free plan,
you picked a type outside the list in section 0; go back and choose `t3.small`.

## 5. Give it a fixed IP (Elastic IP)

An auto-assigned public IP changes every time you stop and start the instance, which would break
your domain. An Elastic IP stays the same and costs the same USD 0.005/hour.

1. EC2 → **Network & Security → Elastic IPs → Allocate Elastic IP address** → *Amazon's pool of
   IPv4 addresses* → **Allocate**.
2. Select the new address → **Actions → Associate Elastic IP address** → Resource type
   **Instance** → choose `trafiqon` → **Associate**.
3. Write down this **Elastic IP**. From now on it is the server's address (the old auto-assigned
   one is released).

An Elastic IP that is **not attached to a running instance still costs** USD 0.005/hour. If you
delete the instance, also **release** the Elastic IP (section 15).

## 6. Connect to the instance

From your computer (PowerShell on Windows 10/11 has `ssh` built in):

```bash
ssh -i ~/.ssh/trafiqon-key.pem ubuntu@ELASTIC_IP
```

On Windows PowerShell write the path as `$env:USERPROFILE\.ssh\trafiqon-key.pem`. The first time,
type `yes` to accept the host fingerprint. The user name is always **`ubuntu`** on Ubuntu AMIs.

No SSH client? EC2 → select the instance → **Connect → EC2 Instance Connect → Connect** opens a
terminal in the browser. It needs port 22 open to AWS's Instance Connect address range; with the
*My IP* rule above it may fail, in which case use `ssh` (or temporarily set the SSH rule to
*Anywhere*, connect, and set it back).

## 7. Prepare the server (updates, swap)

On the server:

```bash
sudo apt-get update && sudo apt-get -y upgrade
```

If it says a restart is required (`ls /var/run/reboot-required` prints a file), run
`sudo reboot`, wait a minute and reconnect.

Add **2 GiB of swap** (insurance for builds and spikes; `t3.small` has 2 GiB of RAM):

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system > /dev/null
free -h
```

`free -h` should show `Swap: 2.0Gi`.

AWS Ubuntu images have the host firewall (`ufw`) **inactive**; the security group from section 4
is the firewall. Leave `ufw` off.

## 8. Get a free domain (DuckDNS)

Let's Encrypt (HTTPS) needs a domain name, not a bare IP.

1. Open the DuckDNS website and sign in (GitHub, Google, ...).
2. Add a subdomain, e.g. `trafiqon-yourname` → `trafiqon-yourname.duckdns.org`.
3. In *current ip*, enter your **Elastic IP** → **update ip**.
4. Check from your computer: `nslookup trafiqon-yourname.duckdns.org` prints the Elastic IP.

(If you own a domain, create an `A` record to the Elastic IP instead.)

## 9. Install Docker

On the server, Docker's official apt repository:

```bash
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
```

**Log out (`exit`) and SSH in again** so the `docker` group applies. Then:

```bash
docker run --rm hello-world
docker compose version
```

`docker compose version` must be **2.24 or newer** (the production file uses `!reset`). Docker
starts at boot, and every TRAFIQON service has `restart: unless-stopped`, so the site comes back
by itself after a reboot or a stop/start of the instance.

## 10. Put your code on GitHub

The server downloads the code from GitHub, so GitHub must have your latest commits, including
`docker-compose.prod.yml`, `deploy/` and this guide. On **your computer**, in the project folder:

```bash
git status -sb
```

- `## main...origin/main` with nothing else: already in sync.
- `[ahead N]`: run `git push`.
- `[ahead N, behind M]`: GitHub has commits you do not have (for example README edits made on
  github.com). Merge them first: `git pull --no-rebase`, resolve any conflict (git lists the
  files), `git commit`, then `git push`.

The repository is public, so the server can clone it without a password. (If you make it private
later, clone with a GitHub personal access token or a deploy key instead.)

## 11. Configure and start TRAFIQON

On the server:

```bash
cd ~
git clone https://github.com/harish05-q/Trafiqon.git trafiqon
cd trafiqon
ls docker-compose.prod.yml deploy/Caddyfile deploy/.env.example
```

The `ls` must list all three files; if not, section 10 was not completed (push, then `git pull`
here).

Generate the two secrets (copy each output somewhere for the next step):

```bash
openssl rand -hex 24
docker run --rm caddy:2.10-alpine caddy hash-password --plaintext 'CHOOSE-A-LOGIN-PASSWORD'
```

The first prints the database password; the second prints a hash starting with `$2a$14$` for the
site login password you chose. Create the settings file:

```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
```

Set these lines (in nano: edit, then `Ctrl+O`, `Enter` to save, `Ctrl+X` to exit):

```ini
SITE_ADDRESS=trafiqon-yourname.duckdns.org
PUBLIC_WEB_URL=https://trafiqon-yourname.duckdns.org
POSTGRES_PASSWORD=<output of openssl rand>
BASIC_AUTH_USER=trafiqon
BASIC_AUTH_HASH='<output of caddy hash-password>'
```

Rules that avoid the usual failures:
- `SITE_ADDRESS`: bare domain, no `https://`, no trailing `/`.
- `POSTGRES_PASSWORD`: letters and digits only (it goes inside a database URL); the hex output is
  safe. It is applied when the database is **first** created; changing it later breaks the login
  (see section 16).
- `BASIC_AUTH_HASH`: keep the **single quotes**; the hash contains `$`.
- `deploy/.env` holds secrets and is git-ignored; never commit it.

Create a short command alias (and keep it for future logins):

```bash
echo "alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file deploy/.env'" >> ~/.bashrc
source ~/.bashrc
```

Build and start (first build: several minutes on `t3.small`; it downloads base images and builds
the web app):

```bash
cd ~/trafiqon
dc up -d --build
dc ps -a
```

Expected `dc ps -a`:

| Service | State |
|---|---|
| db, api, web | running (**healthy**) |
| worker, caddy | running |
| migrate | **exited (0)**: a one-shot job that applies database migrations, then exits. Correct. |

Do not add `--wait`; it reports an error because the worker deliberately has no healthcheck.
If something is not up, run `dc logs <service>` and see section 16.

## 12. Check that it works

1. Open `https://trafiqon-yourname.duckdns.org`. The first visit can take up to a minute while
   Caddy obtains the certificate (`dc logs caddy` shows `certificate obtained successfully`).
2. A login prompt appears: user `trafiqon` (or what you set), and the password you hashed.
3. The top bar shows **API: online · DB: ok**.
4. Command Center → import a built-in scenario → **Launch run**. It goes QUEUED → RUNNING →
   COMPLETED with a live event log, and is still there after a page reload.

From any terminal:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://trafiqon-yourname.duckdns.org/
curl -s -u trafiqon:YOUR_PASSWORD https://trafiqon-yourname.duckdns.org/api/v1/ready
```

The first prints `401` (password required), the second `{"ready":true,...}`.

## 13. Day-to-day operations

On the server, in `~/trafiqon`:

| Task | Command |
|---|---|
| Status | `dc ps -a` |
| Logs (follow) | `dc logs -f --tail 100 api worker` |
| Restart a service | `dc restart worker` |
| Stop the app (keeps data) | `dc down` |
| Start the app | `dc up -d` |
| Deploy new code | `git pull && dc up -d --build` (migrations run automatically) |
| Free disk | `docker image prune -f && docker builder prune -f` |
| Disk / memory | `df -h /` and `free -h` |

**Backups.** The database lives on the instance's disk. If the account closes, it is gone, so
copy backups to your own computer.

```bash
mkdir -p ~/backups
dc exec -T db pg_dump -U trafiqon -d trafiqon --format=custom > ~/backups/trafiqon-$(date +%F).dump
```

Nightly at 03:00 server time (UTC), keeping 14 days: `crontab -e`, choose nano, add one line:

```
0 3 * * * cd /home/ubuntu/trafiqon && docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file deploy/.env exec -T db pg_dump -U trafiqon -d trafiqon --format=custom > /home/ubuntu/backups/trafiqon-$(date +\%F).dump && find /home/ubuntu/backups -name '*.dump' -mtime +14 -delete
```

Download one to your computer (run on your computer):

```bash
scp -i ~/.ssh/trafiqon-key.pem ubuntu@ELASTIC_IP:backups/trafiqon-YYYY-MM-DD.dump .
```

**Restore** (replaces the current data):

```bash
dc stop api worker
dc exec -T db pg_restore -U trafiqon -d trafiqon --clean --if-exists --no-owner < ~/backups/trafiqon-YYYY-MM-DD.dump
dc start api worker
```

**What a restart loses.** Scenarios, runs, results and suites are in Postgres and survive
restarts and instance stop/start. Live **simulation sessions** are kept in API memory (STATUS.md
D27) and end when the API restarts; the UI says so.

**Keep it small.** `t3.small` executes one run at a time. To stop visitors from queueing long
jobs, lower the limits (names in `docs/api_contracts.md`), e.g. add under `api:` →
`environment:` in `docker-compose.prod.yml`:

```yaml
      TRAFIQON_LIMIT_MAX_QUEUED_RUNS: "20"
      TRAFIQON_LIMIT_MAX_TIME_LIMIT_S: "60"
```

then `dc up -d`.

## 14. Saving credits

- **Stop the instance when you are not using it:** EC2 → Instances → select → **Instance state →
  Stop instance**. Compute billing stops; the disk (~USD 1.6/month) and Elastic IP (~USD 3.7/month)
  still bill. **Start instance** brings the site back automatically at the same address (Elastic
  IP); data is kept. Do not choose *Terminate* unless you want to delete it.
- Check **Billing and Cost Management → Credits** every week or two, and react to the budget
  e-mails.
- Before a demo, start the instance about 3 minutes early.

## 15. Before the Free plan ends / shutting down

Before the plan end date (section 1) or before credits run out:

1. Take a fresh backup and download it (section 13).
2. Decide: **upgrade to the Paid plan** (Billing console → upgrade; remaining credits still apply,
   then normal charges to your payment method) or **let the account close**.

To delete everything yourself (stops all credit use):

1. EC2 → Instances → select `trafiqon` → **Instance state → Terminate** (this deletes the disk
   too, because Ubuntu AMIs delete the root volume on termination by default).
2. EC2 → **Elastic IPs** → select it → **Actions → Release Elastic IP addresses**.
3. EC2 → **Volumes** and **Snapshots**: delete anything left over.
4. EC2 → **Key Pairs** and **Security Groups**: deleting `trafiqon-key` and `trafiqon-sg` is
   optional (they cost nothing).
5. A day later, check **Billing → Bills** for that region shows no running usage.

## 16. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ssh: connect ... timed out` | Your home IP changed (common with mobile/broadband ISPs), so the *My IP* SSH rule no longer matches. EC2 → Security Groups → `trafiqon-sg` → Edit inbound rules → SSH → Source *My IP* again → Save. Also check the instance is *Running* and you use the **Elastic IP**. |
| `Permission denied (publickey)` | Wrong user (must be `ubuntu`) or wrong key file. |
| `WARNING: UNPROTECTED PRIVATE KEY FILE!` | Run the `icacls` (Windows) or `chmod 400` commands from section 3. |
| Instance type "not eligible" on launch | Only the Free-tier-eligible types work on the Free plan (section 0). Use `t3.small`. |
| Browser cannot connect / no certificate; `dc logs caddy` shows `timeout during connect` or `challenge failed` | HTTP 80 and HTTPS 443 must be open to *Anywhere* in `trafiqon-sg`, and DuckDNS must point to the **Elastic IP**. Fix, then `dc restart caddy`. |
| Certificate errors after many attempts | Let's Encrypt rate limits repeated failures. Fix the cause, wait an hour, `dc restart caddy`. Do not delete the `caddy_data` volume repeatedly. |
| `required variable ... is missing` | A line is missing in `deploy/.env`, or you ran plain `docker compose` instead of the `dc` alias. |
| Login prompt rejects the right password | The hash lost its `$` signs: it must be in single quotes in `deploy/.env`. Then `dc up -d`. Check: `dc exec caddy printenv BASIC_AUTH_HASH` starts with `$2a$`. |
| `migrate` exited 1, `api` never starts | DB password mismatch, usually because `POSTGRES_PASSWORD` was changed after the first start. `dc logs migrate` shows it. Put the original password back, or (deletes all data) `dc down -v` and `dc up -d --build`. |
| Build stops with `Killed` or `exit code 137` | Out of memory: check swap is on (`free -h`, section 7), then rerun `dc up -d --build`. |
| Top bar says **API: offline** | `dc ps -a`, `dc logs api`. If you changed the compose files, rebuild the web app: `dc up -d --build web`. |
| Runs stay QUEUED | Worker down: `dc logs worker`, `dc restart worker`. |
| Site very slow during long runs | Standard-mode CPU credits used up; it recovers when idle. Lower run limits (section 13). `t3.small` is a small machine. |
| Disk full (`no space left on device`) | `docker image prune -f && docker builder prune -f`; delete old backups. |
| `!reset` / unknown tag error | Compose older than 2.24: reinstall `docker-compose-plugin` (section 9). |
| Budget e-mail at 80 % | Stop the instance when idle (section 14), or plan the end date (section 15). |

## 17. Alternative: your own computer + Cloudflare quick tunnel

For a short demo with no cloud at all: run the production stack on your own machine and expose it
through a Cloudflare *quick tunnel* (free, no account, random temporary URL). It works only while
your computer is on.

1. In `deploy/.env`: `SITE_ADDRESS=:80`, `HTTP_PORT=8088`, `HTTPS_PORT=8443`,
   `PUBLIC_WEB_URL=http://localhost:8088`, plus the password and hash as in section 11.
2. `docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file deploy/.env up -d --build`,
   then open `http://localhost:8088`.
3. Install `cloudflared` from Cloudflare's downloads page and run
   `cloudflared tunnel --url http://localhost:8088`. It prints a `https://….trycloudflare.com` URL.

Steps 1-2 are verified; the tunnel itself was not tested.

## 18. What was verified

On the development machine (Windows 11, Docker Desktop, Compose 2.39), using exactly
`docker-compose.yml` + `docker-compose.prod.yml` + `deploy/Caddyfile` with `SITE_ADDRESS=:80` on
host port 8088 (2026-10-29/30):
- Only Caddy publishes ports. Without the password, page and API return 401; with it, 200.
- Runs submitted through Caddy are executed by the worker container; SSE progress arrives through
  the proxy. In a real browser every request goes to the single site address.
- Data survives `down`/`up`; `pg_dump` and both restore paths work.
- **Memory (for sizing t3.small):** idle stack about 280 MiB in total; while executing nine runs
  (QPSO 150 iterations, OR-Tools, SA 200k moves on each built-in scenario) plus a simulation
  session, peaks were api 102, db 84, worker 74, web 41, caddy 13 MiB (sum of peaks 313 MiB).
  The web production build completed inside a container capped at 1.5 GiB with no swap
  (peak resident memory about 940 MiB, 58 s on 2 CPUs of the dev machine; a t3.small will be
  slower).
- Images: backend 1.5 GB (shared by api, worker, migrate), web 340 MB, postgres 644 MB, caddy
  83 MB.
- The backend image also builds and solves on `linux/arm64` (emulated).

**Not verified here:** an actual EC2 instance, the AWS console steps (they follow AWS's current
documentation, and the console layout can change), AWS prices in your region, Let's Encrypt on a
public domain, DuckDNS, and the Cloudflare tunnel.

Sources for the AWS facts in section 0: AWS Free Tier page and FAQs (aws.amazon.com/free), "Choosing
an AWS Free Tier plan" (AWS Billing docs), "EC2 Free Tier usage" (EC2 user guide), Amazon VPC
pricing (public IPv4), EC2 burstable instances unlimited mode docs and EC2 on-demand pricing
(surplus credits).
