# math-high

Simple three-tier webapp: **Vue 3** frontend, **FastAPI** backend, **SQLite** (swappable to Postgres later), deployed natively (no Docker) to a Linux VPS via GitHub Actions on every push to `main`.

```
api/    FastAPI backend (runs as a systemd service via uvicorn)
web/    Vue 3 + Vite frontend (built to static files, served by nginx)
deploy/ VPS setup script, systemd unit, nginx site config
```

## Architecture

- **api**: FastAPI + SQLAlchemy, runs as the `math-high-api` systemd service, uvicorn bound to `127.0.0.1:8000` (not exposed externally).
- **web**: Vue 3 built to static files (`web/dist`), served directly by nginx.
- **nginx**: serves the built frontend and reverse-proxies `/api/*` to the FastAPI service, so the browser only ever talks to one origin — no CORS needed in production. Add TLS via certbot once your domain's DNS is set up (see below).
- **SQLite**: `api/data/app.db`, a plain file on disk. Nothing else to run or manage.

## Local development

```bash
# API
cd api
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
alembic upgrade head                              # build the SQLite schema (creates data/app.db)
python -m app.ingest                              # load pilot course content (idempotent)
uvicorn app.main:app --reload

# Web (separate terminal)
cd web
npm install
npm run dev
```

Vite's dev server proxies `/api/*` to `http://localhost:8000` (see `web/vite.config.js`), matching how nginx proxies in production — the frontend code never needs to know which environment it's in.

Visit http://localhost:5173.

## Deploying to a VPS

Full detail — topology, config vars, HTTPS, CI/CD, server layout, troubleshooting —
is in [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md). Quick version below.

### 0. Current deployment

| | |
|---|---|
| Host | `mentisq-dreamit` (`202.37.74.65`), Ubuntu 22.04 LTS |
| Domain | https://math.mentisq.com (TLS via Let's Encrypt/certbot, auto-renews; HTTP redirects to HTTPS) |
| Deploy user | `deploy`, key-only for app deploys, sudo scoped to just `systemctl restart math-high-api` / `systemctl reload nginx` |
| App dir | `/home/deploy/math-high` |
| Repo | https://github.com/iftekhar41d/math_high (public) |

The steps below are what was actually run to get there, kept general so the same flow reproduces on a new VPS.

### 1. Bootstrap SSH key access

A fresh VPS typically only has password login. Generate a dedicated deploy key (no passphrase, so CI can use it non-interactively) and install it:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/math_high_deploy -N "" -C "math-high-deploy"
ssh-copy-id -i ~/.ssh/math_high_deploy.pub deploy@<vps-ip>   # prompts once for the account password
ssh -i ~/.ssh/math_high_deploy deploy@<vps-ip> echo ok       # confirm key-based login works
```

This only touches `~/.ssh/authorized_keys` for the `deploy` user — it doesn't disable password authentication, so password login stays available as a fallback unless you deliberately turn it off in `sshd_config` later.

### 2. Run the server setup script

`setup-vps.sh` reads its settings — `DOMAIN`, `REPO_URL`, `APP_DIR`,
`LETSENCRYPT_EMAIL` — from a CONFIG block at the top of the script, each with a
default. Override any of them per run with a positional arg **or** an env var of
the same name (arg wins):

```bash
./setup-vps.sh                                 # baked-in defaults (this deployment)
./setup-vps.sh app.example.com                 # just a different domain
DOMAIN=app.example.com \
  REPO_URL=https://github.com/you/fork.git \
  LETSENCRYPT_EMAIL=you@example.com ./setup-vps.sh
```

`setup-vps.sh` needs `sudo` for package installs, the systemd unit, and the nginx site — none of which can be scripted through an interactive password prompt over SSH. Either run it yourself (typing the sudo password at each prompt), or, for unattended setup, grant the deploy user temporary passwordless sudo, run the script, then revoke it:

```bash
# on the VPS, or via ssh -i ~/.ssh/math_high_deploy deploy@<vps-ip>
echo "$(whoami) ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/91-temp-full-setup
sudo chmod 440 /etc/sudoers.d/91-temp-full-setup

curl -fsSL https://raw.githubusercontent.com/iftekhar41d/math_high/main/deploy/setup-vps.sh -o setup-vps.sh
chmod +x setup-vps.sh
LETSENCRYPT_EMAIL=you@example.com ./setup-vps.sh app.example.com

sudo rm -f /etc/sudoers.d/91-temp-full-setup   # setup-vps.sh already installed the narrow rule it actually needs
```

This installs Python, Node.js, and nginx; clones the repo; sets up the API's venv; builds the frontend; installs and starts the `math-high-api` systemd service; configures the nginx site; grants the deploy user passwordless sudo scoped to *only* `systemctl restart math-high-api` and `systemctl reload nginx` (needed for CI/CD to restart the app non-interactively — nothing broader); and, when `LETSENCRYPT_EMAIL` is set and the domain already resolves to the VPS, runs certbot to provision HTTPS non-interactively (HTTP → HTTPS redirect included).

Re-running the script on an already-provisioned host is safe — it will not
overwrite a Certbot-managed nginx config unless you pass `FORCE_NGINX=1`.

If you left `LETSENCRYPT_EMAIL` unset, or DNS wasn't pointing at the VPS yet,
enable HTTPS later with:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <your-domain>
```

### 3. GitHub Actions CI/CD

`.github/workflows/deploy.yml` SSHes into the VPS on every push to `main` and runs: `git reset --hard origin/main`, reinstalls Python/Node dependencies, runs `alembic upgrade head`, loads course content with `python -m app.ingest` (idempotent), rebuilds the frontend, then restarts the API service and reloads nginx.

Add these **repository secrets** (Settings → Secrets and variables → Actions):

| Secret        | Value                                                              |
|---------------|---------------------------------------------------------------------|
| `VPS_HOST`    | VPS IP or hostname                                                  |
| `VPS_USER`    | SSH user (the one `setup-vps.sh` ran as)                            |
| `VPS_SSH_KEY` | Private key generated in step 1 (`~/.ssh/math_high_deploy`, the whole file including the `BEGIN`/`END` lines) |
| `VPS_PORT`    | SSH port, optional (defaults to 22)                                 |
| `APP_DIR`     | Absolute path to the cloned repo on the VPS, e.g. `/home/deploy/math-high` |

Push to `main` and the workflow deploys automatically. Check progress under the repo's **Actions** tab, or `gh run list` / `gh run watch` if you have the GitHub CLI authenticated.

## Migrating from SQLite to Postgres later

1. Install Postgres on the VPS (`sudo apt-get install postgresql`) or point at a managed instance.
2. Add `psycopg[binary]` to `api/requirements.txt` and reinstall (`.venv/bin/pip install -r requirements.txt`).
3. Add an `Environment=DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app` line to `/etc/systemd/system/math-high-api.service`.
4. With that `DATABASE_URL` set, run `alembic upgrade head` from `api/` to build the schema on Postgres, then `sudo systemctl daemon-reload && sudo systemctl restart math-high-api`.

No application code changes needed — `api/app/database.py` and `api/migrations/env.py` both read `DATABASE_URL` directly, defaulting to the local SQLite file when unset. The Alembic migrations are written portably (association tables, string enums) so they replay against Postgres.
