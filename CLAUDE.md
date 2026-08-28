# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### API (`api/`)
Run everything from inside `api/` — the module path is `app.*` and the default
`DATABASE_URL` (`sqlite:///./data/app.db`) is resolved relative to the CWD.

```bash
cd api
python -m venv .venv && .venv/Scripts/activate   # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head                              # build the schema (creates data/app.db)
uvicorn app.main:app --reload                     # http://localhost:8000, docs at /docs
```

Tests: `pytest` (from `api/`). The harness is `tests/conftest.py` — FastAPI
`TestClient`, an ephemeral in-memory SQLite DB per test, and dependency-override
fakes for the three boundary adapters (`Clock`, `EmailSender`,
`MentisQLLMClient`). Tests assert on HTTP responses and persisted state, not
internals.

### Web (`web/`)
```bash
cd web
npm install
npm run dev        # http://localhost:5173, proxies /api -> localhost:8000
npm run build      # outputs static files to web/dist (what nginx serves in prod)
npm run preview    # serve the production build locally
```

There are no linters or formatters configured in this repo.

## Architecture

Three tiers, deployed natively (no Docker) to a single Linux VPS:

- **`web/`** — Vue 3 + Vite SPA (`<script setup>`) with **Vue Router** (`web/src/router/`,
  history mode) and **Pinia** (`web/src/stores/`); no Vuex. Screens live in
  `web/src/views/`. Built to `web/dist`, served as static files by nginx.
- **`api/`** — FastAPI + SQLAlchemy 2.0 (typed `Mapped[...]` models). Runs as the
  `math-high-api` systemd service: uvicorn bound to `127.0.0.1:8000`, never exposed
  directly.
- **SQLite** — `api/data/app.db`, a plain file. No DB server to manage.

### The `/api` proxy convention
Frontend code always calls same-origin relative paths under `/api` (`web/src/api.js`).
Both proxies **strip the `/api` prefix** before forwarding to FastAPI:

- Dev: Vite `server.proxy` in `web/vite.config.js` rewrites `/api/*` → `localhost:8000/*`.
- Prod: nginx `location /api/` → `proxy_pass http://127.0.0.1:8000/` (`deploy/nginx.conf`).

**Therefore FastAPI routers must NOT include an `/api` prefix** — e.g. the meta
router is mounted at `/meta`, reached in the browser as `/api/meta`. Because prod
is single-origin, no CORS is needed there; the CORS middleware in `app/main.py` exists
only for local dev (configurable via `CORS_ORIGINS`).

### Database lifecycle
**Alembic is the schema source of truth** (`api/migrations/`). `app/main.py` does
**not** create tables on startup — run `alembic upgrade head` (locally, in
`setup-vps.sh`, and in the deploy workflow before the service restart). Add a
model → generate a migration:

```bash
cd api
alembic revision --autogenerate -m "add users table"   # review the generated file
alembic upgrade head
```

`migrations/env.py` targets `Base.metadata` via `import app.models` and reads the
same `DATABASE_URL` env var + default as `app/database.py`. SQLite migrations run
in batch mode (SQLite can't `ALTER`). The test harness applies schema with
`Base.metadata.create_all` on an ephemeral engine for speed; `tests/test_migrations.py`
covers the Alembic path itself.

`app/database.py` reads `DATABASE_URL` from the environment, defaulting to local
SQLite. Switching to Postgres is env-only (add `psycopg[binary]`, set an
`Environment=DATABASE_URL=postgresql+psycopg://...` line in the systemd unit, run
`alembic upgrade head`) — no application code changes. See README "Migrating from
SQLite to Postgres later".

### External-boundary adapters
Three seams isolate the app from the outside world, each a FastAPI dependency
with a real implementation and an in-memory test fake:
`Clock` (`app/clock.py`, injectable `now()`), `EmailSender` (`app/email_sender.py`,
outbound email; logs instead of sending when `SMTP_HOST` is unset), and
`MentisQLLMClient` (`app/mentisq/llm_client.py`, the only code that talks to
OpenRouter; 30s timeout; key from `OPENROUTER_API_KEY`, never the DB). Override
them with `app.dependency_overrides` in tests; don't reach past them.

### Auth (`app/auth/`)
`AuthService` (`app/auth/service.py`) is the reusable core — registration, email
verification, login, rotating refresh sessions, password reset, login rate
limiting — and reads time only through the injected `Clock`. The routers
(`app/routers/auth.py`, `.../profile.py`) are thin HTTP wrappers that own status
codes, the refresh cookie, and outbound email. Access tokens are short-lived
HS256 JWTs (`app/auth/jwt.py`) carrying the user's `token_generation`; bumping
that (logout-all, password reset) invalidates every outstanding access **and**
refresh token. Protect an endpoint with `Depends(require_verified_user)` from
`app/auth/dependencies.py`. Config/tunables (TTLs, `JWT_SECRET`,
`AUTH_COOKIE_SECURE`, `PUBLIC_BASE_URL`) live in `app/auth/config.py`, all
env-overridable; prod values come from `/etc/math-high-api.env`.

### Adding an endpoint
1. Model in `app/models.py`, then `alembic revision --autogenerate -m "..."` and
   review the migration. Pydantic schemas in `app/schemas.py` (use
   `ConfigDict(from_attributes=True)` to serialize ORM objects).
2. New router in `app/routers/`, `app.include_router(...)` it in `app/main.py`.
3. Use the `Depends(get_db)` session dependency; no `/api` prefix on the router.
4. Add a `pytest` test in `api/tests/` exercising it through the `client` fixture.

## Deployment

Full reference: [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md).

Push to `main` → `.github/workflows/deploy.yml` SSHes into the VPS and runs:
`git reset --hard origin/main` → `pip install -r requirements.txt` →
`alembic upgrade head` → `npm install && npm run build` →
`systemctl restart math-high-api` + `reload nginx`.

The deploy user's sudo is scoped to exactly those two `systemctl` commands. A fresh
VPS is bootstrapped once with `deploy/setup-vps.sh [domain] [repo-url] [app-dir]`
(installs Python/Node/nginx, venv, systemd unit, nginx site, scoped sudoers rule).
Every setting has a default in the script's CONFIG block and is overridable by a
positional arg or a same-named env var; set `LETSENCRYPT_EMAIL` to also run certbot
non-interactively. The nginx template lives at [deploy/nginx.conf](deploy/nginx.conf)
with a `__DOMAIN__` placeholder that `sed` fills in at setup time — the live per-host
config is `/etc/nginx/sites-available/math-high` on the VPS, not in the repo.
Current host: `math.mentisq.com` (Ubuntu 22.04, app dir `/home/deploy/math-high`).
Required GitHub repo secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `APP_DIR`,
optional `VPS_PORT`.

## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/<feature-slug>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Design System
Always use these colors — never invent new hex values:
- Background: #F9F7F7
- Accent: #DBE2EF
- Primary: #3F72AF
- Dark/Text: #112D4E
