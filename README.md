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
uvicorn app.main:app --reload

# Web (separate terminal)
cd web
npm install
npm run dev
```

Vite's dev server proxies `/api/*` to `http://localhost:8000` (see `web/vite.config.js`), matching how nginx proxies in production — the frontend code never needs to know which environment it's in.

Visit http://localhost:5173.

## Deploying to a VPS

### One-time server setup

On a fresh Ubuntu/Debian VPS, as a non-root user with sudo access:

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/setup-vps.sh -o setup-vps.sh
chmod +x setup-vps.sh
./setup-vps.sh git@github.com:<you>/<repo>.git your-domain.com
```

This installs Python, Node.js, and nginx; clones the repo; sets up the API's venv; builds the frontend; installs and starts the `math-high-api` systemd service; configures the nginx site; and grants the deploy user passwordless sudo scoped to *only* `systemctl restart math-high-api` and `systemctl reload nginx` (needed for CI/CD to restart the app non-interactively — nothing broader).

Make sure your domain's DNS A record points at the VPS, then enable HTTPS:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### GitHub Actions CI/CD

`.github/workflows/deploy.yml` SSHes into the VPS on every push to `main` and runs: `git reset --hard origin/main`, reinstalls Python/Node dependencies, rebuilds the frontend, then restarts the API service and reloads nginx.

Add these **repository secrets** (Settings → Secrets and variables → Actions):

| Secret        | Value                                                              |
|---------------|---------------------------------------------------------------------|
| `VPS_HOST`    | VPS IP or hostname                                                  |
| `VPS_USER`    | SSH user (the one `setup-vps.sh` ran as)                            |
| `VPS_SSH_KEY` | Private key for that user (add the matching public key to the VPS's `~/.ssh/authorized_keys`) |
| `VPS_PORT`    | SSH port, optional (defaults to 22)                                 |
| `APP_DIR`     | Absolute path to the cloned repo on the VPS, e.g. `/home/deploy/math-high` |

Push to `main` and the workflow deploys automatically. Check progress under the repo's **Actions** tab.

## Migrating from SQLite to Postgres later

1. Install Postgres on the VPS (`sudo apt-get install postgresql`) or point at a managed instance.
2. Add `psycopg[binary]` to `api/requirements.txt` and reinstall (`.venv/bin/pip install -r requirements.txt`).
3. Add an `Environment=DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app` line to `/etc/systemd/system/math-high-api.service`, then `sudo systemctl daemon-reload && sudo systemctl restart math-high-api`.

No application code changes needed — `api/app/database.py` reads `DATABASE_URL` directly, defaulting to the local SQLite file when unset.
