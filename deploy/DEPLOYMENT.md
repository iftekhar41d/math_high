# Deployment

How `math-high` gets onto a Linux VPS and stays there. Native install, no Docker:
the API runs as a systemd service behind nginx, the frontend is static files nginx
serves directly, and every push to `main` redeploys via GitHub Actions.

- [Topology](#topology)
- [Files in this directory](#files-in-this-directory)
- [Configuration](#configuration)
- [Standing up a new VPS](#standing-up-a-new-vps)
- [HTTPS / TLS](#https--tls)
- [CI/CD](#cicd)
- [Re-running setup on an existing host](#re-running-setup-on-an-existing-host)
- [Where things live on the server](#where-things-live-on-the-server)
- [Operations](#operations)
- [Troubleshooting](#troubleshooting)
- [Current deployment](#current-deployment)

## Topology

```
                     :80 / :443
  browser  ─────────────────────────►  nginx
                                        │
                        static files    ├── /            → APP_DIR/web/dist  (Vue build)
                        reverse proxy    └── /api/*       → 127.0.0.1:8000/*  (strips /api)
                                                                │
                                                          uvicorn (systemd: math-high-api)
                                                          FastAPI app, 2 workers
                                                                │
                                                          SQLite file: APP_DIR/api/data/app.db
```

- uvicorn binds `127.0.0.1:8000` only — never reachable from outside the box.
- nginx is the single public origin, so production needs no CORS.
- The `/api` prefix is a client-side convention only; **both** the Vite dev proxy
  and the nginx `location /api/` block strip it before forwarding, so FastAPI
  routers carry no `/api` prefix.

## Files in this directory

| File | Role | Templated? |
|---|---|---|
| `setup-vps.sh` | One-time provisioning script, run on the VPS | — |
| `nginx.conf` | nginx site template | `__DOMAIN__`, `__APP_DIR__` filled by `sed` at setup |
| `math-high-api.service` | systemd unit template | `__DEPLOY_USER__`, `__APP_DIR__` filled by `sed` at setup |
| `../.github/workflows/deploy.yml` | GitHub Actions deploy job (SSH) | — |
| `check-vps-usage.sh` | Local-only ops helper, **git-ignored** (hardcodes this host) | — |

The templates in this repo contain placeholders. The concrete, filled-in copies
live on the server (see [Where things live](#where-things-live-on-the-server)) —
the repo never stores a real domain in an active config file, only in docs.

## Configuration

`setup-vps.sh` has a CONFIG block at the top. Each value has a default and is
overridable per run by a **positional arg** or an **environment variable of the
same name** (the positional arg wins):

```
./setup-vps.sh [domain] [repo-url] [app-dir]
```

| Setting | Default | Notes |
|---|---|---|
| `DOMAIN` | `math.mentisq.com` | nginx `server_name`; also the cert domain |
| `REPO_URL` | `https://github.com/iftekhar41d/math_high.git` | cloned to `APP_DIR` |
| `APP_DIR` | `$HOME/math-high` | repo checkout root on the server |
| `LETSENCRYPT_EMAIL` | *(empty)* | set it to provision HTTPS automatically; empty = skip, print manual steps |
| `FORCE_NGINX` | `0` | `1` = regenerate the nginx site even if Certbot has edited it |

Examples:

```bash
./setup-vps.sh                                   # reproduce the current deployment
./setup-vps.sh app.example.com                   # new domain, everything else default
DOMAIN=app.example.com \
  REPO_URL=https://github.com/you/fork.git \
  LETSENCRYPT_EMAIL=you@example.com ./setup-vps.sh
```

## Standing up a new VPS

Assumes a fresh Ubuntu/Debian box and a non-root user with sudo (referred to here
as `deploy`).

### 1. DNS

Point an `A` record for your domain at the VPS IP before running certbot, or HTTPS
provisioning will be skipped (the rest of setup still succeeds).

### 2. SSH key (from your machine)

CI needs a passphrase-less key it can use non-interactively:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/math_high_deploy -N "" -C "math-high-deploy"
ssh-copy-id -i ~/.ssh/math_high_deploy.pub deploy@<vps-ip>   # prompts once for the password
ssh -i ~/.ssh/math_high_deploy deploy@<vps-ip> echo ok       # confirm
```

This only appends to `~deploy/.ssh/authorized_keys`; it does not disable password
login.

### 3. Run the setup script (on the VPS)

`setup-vps.sh` needs sudo for apt, the systemd unit, and the nginx site. Run it
and type the sudo password when prompted:

```bash
curl -fsSL https://raw.githubusercontent.com/iftekhar41d/math_high/main/deploy/setup-vps.sh -o setup-vps.sh
chmod +x setup-vps.sh
LETSENCRYPT_EMAIL=you@example.com ./setup-vps.sh app.example.com
```

For a fully unattended run, grant temporary passwordless sudo, run it, then revoke
(the script installs the narrow rule it actually needs itself):

```bash
echo "$(whoami) ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/91-temp-full-setup
sudo chmod 440 /etc/sudoers.d/91-temp-full-setup

LETSENCRYPT_EMAIL=you@example.com ./setup-vps.sh app.example.com

sudo rm -f /etc/sudoers.d/91-temp-full-setup
```

What the script does, in order:

1. `apt-get install` git, python3 (+venv/pip), nginx, curl; Node.js 20.x from
   NodeSource if `node` is missing.
2. Opens ufw for OpenSSH / 80 / 443 (only if ufw is present).
3. Clones `REPO_URL` to `APP_DIR` (or `git pull` if already there).
4. Creates `api/.venv`, installs `api/requirements.txt`, runs
   `alembic upgrade head` to build the database schema.
5. `npm install && npm run build` in `web/` → `web/dist`.
6. Writes `/etc/math-high-api.env` (mode 600) if absent, with a freshly
   generated `JWT_SECRET`, `PUBLIC_BASE_URL=https://$DOMAIN`,
   `AUTH_COOKIE_SECURE=1`, and commented placeholders for `OPENROUTER_API_KEY`
   and the `SMTP_*` vars. The systemd unit loads it via `EnvironmentFile=-`.
   Re-running setup never overwrites an existing file — edit it in place to add
   the email / LLM credentials, then `sudo systemctl restart math-high-api`.
7. Renders `math-high-api.service` → `/etc/systemd/system/`, `daemon-reload`,
   `enable --now`.
8. Renders `nginx.conf` → `/etc/nginx/sites-available/math-high`, symlinks it into
   `sites-enabled/`, removes the default site, `nginx -t`, `reload`.
9. Writes `/etc/sudoers.d/math-high-deploy` granting the deploy user passwordless
   sudo for **exactly** `systemctl restart math-high-api` and
   `systemctl reload nginx` — nothing else — then `visudo -c` to validate.
10. If `LETSENCRYPT_EMAIL` is set and `DOMAIN` resolves: installs certbot and runs
    it non-interactively with `--redirect`.
11. Prints the app dir, service status command, and the exact GitHub secret values
    to set.

### 4. GitHub repo secrets

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | the deploy user (whoami during setup) |
| `VPS_SSH_KEY` | contents of `~/.ssh/math_high_deploy` (the whole file, incl. `BEGIN`/`END`) |
| `APP_DIR` | absolute path to the checkout, e.g. `/home/deploy/math-high` |
| `VPS_PORT` | SSH port — optional, defaults to `22` |

### 5. Deploy

Push to `main`. Watch it under the repo's **Actions** tab, or
`gh run list` / `gh run watch`.

## HTTPS / TLS

- **Automatic:** pass `LETSENCRYPT_EMAIL` to `setup-vps.sh` with DNS already
  pointing at the box. It runs
  `certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL --redirect`,
  which also rewrites the nginx site to add the `listen 443` block and the
  HTTP→HTTPS redirect. Renewal is handled by certbot's systemd timer.
- **Manual / later:** if DNS wasn't ready or you left the email unset:

  ```bash
  sudo apt-get install -y certbot python3-certbot-nginx
  sudo certbot --nginx -d <your-domain>
  ```

- The email is deliberately **not** stored in the repo — it would be published and
  registered with Let's Encrypt. Keep it in the command line / an env var.

## CI/CD

`.github/workflows/deploy.yml` runs on every push to `main`. It SSHes in
(`appleboy/ssh-action`) and runs, in `APP_DIR`:

```
git fetch origin main
git reset --hard origin/main          # server-side local changes are discarded
cd api && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head        # apply migrations before the restart
cd ../web && npm install && npm run build
sudo systemctl restart math-high-api
sudo systemctl reload nginx
```

It never touches nginx `server_name`, the systemd unit, or TLS — those are set
once by `setup-vps.sh` and by certbot. Schema changes are Alembic migrations
(`api/migrations/`): `alembic upgrade head` runs on every deploy, before the
service restart, so the schema is in step with the code being started.

## Re-running setup on an existing host

`setup-vps.sh` is close to idempotent — `git pull` instead of clone, `enable --now`,
`ln -sf`, `visudo -c`. The one hazard is the nginx site file: certbot edits it, and
a plain re-run would overwrite those edits from `nginx.conf`. The script guards
this: if the file contains `# managed by Certbot` it is left untouched unless you
pass `FORCE_NGINX=1`.

## Where things live on the server

| Path | What |
|---|---|
| `APP_DIR` (`/home/deploy/math-high`) | repo checkout |
| `APP_DIR/api/.venv` | API virtualenv |
| `APP_DIR/api/data/app.db` | SQLite database (survives deploys; **not** in git) |
| `APP_DIR/web/dist` | built frontend nginx serves |
| `/etc/systemd/system/math-high-api.service` | rendered unit (real user/paths) |
| `/etc/math-high-api.env` | runtime secrets/config (`JWT_SECRET`, `PUBLIC_BASE_URL`, later `OPENROUTER_API_KEY` / `SMTP_*`); mode 600, **not** in git |
| `/etc/nginx/sites-available/math-high` | rendered site (real domain, + certbot's 443 block) |
| `/etc/nginx/sites-enabled/math-high` | symlink to the above |
| `/etc/sudoers.d/math-high-deploy` | the two-command NOPASSWD rule for CI |
| `/etc/letsencrypt/live/<domain>/` | TLS cert + key |

## Operations

```bash
sudo systemctl status math-high-api          # is the API up?
journalctl -u math-high-api -f               # API logs (uvicorn/app stdout+stderr)
sudo systemctl restart math-high-api         # restart API
sudo tail -f /var/log/nginx/{access,error}.log
sudo nginx -t && sudo systemctl reload nginx # test + apply nginx changes
curl -s localhost:8000/health                # API healthcheck (on the box)
curl -s https://<domain>/api/health          # end-to-end through nginx
```

Reset the dev/prod database (destroys all data): stop the service, delete
`api/data/app.db`, run `.venv/bin/alembic upgrade head` from `api/`, start the
service — the schema is rebuilt empty from the migrations.

## Migrating SQLite → Postgres

No application code changes; `api/app/database.py` reads `DATABASE_URL` (defaults
to the local SQLite file when unset).

1. `sudo apt-get install postgresql`, create a db/user, or use a managed instance.
2. Add `psycopg[binary]` to `api/requirements.txt`, reinstall in the venv.
3. Add to `/etc/systemd/system/math-high-api.service` under `[Service]`:
   `Environment=DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app`
4. With that `DATABASE_URL` exported, run `.venv/bin/alembic upgrade head` from
   `api/` to build the schema on Postgres (the migrations are portable).
5. `sudo systemctl daemon-reload && sudo systemctl restart math-high-api`.

## Current deployment

| | |
|---|---|
| Host | `mentisq-dreamit` (`202.37.74.65`), Ubuntu 22.04 LTS |
| Domain | https://math.mentisq.com — TLS via Let's Encrypt, auto-renews, HTTP→HTTPS |
| Deploy user | `deploy` (key-only; sudo scoped to the two `systemctl` commands) |
| App dir | `/home/deploy/math-high` |
| Repo | https://github.com/iftekhar41d/math_high (public) |
