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
python -m app.ingest                              # load pilot course content (idempotent)
uvicorn app.main:app --reload                     # http://localhost:8000, docs at /docs
```

`python -m app.ingest [manifest]` loads the course tree, lecture Markdown, and
questions from `api/content/` (default `content/manifest.yaml`) into the DB. It
is safe to re-run — every entity is upserted by slug — and rejects a malformed
manifest without writing anything. See the "Content seeding" architecture note.

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

### Media storage (`app/storage.py`)
Lecture images go through a `save` / `get_url` seam (`MediaStorage`), so moving
off local disk to S3/R2 later is one class. Phase 1 impl is `LocalMediaStorage`
(files under `MEDIA_ROOT`, default `api/data/media/`); URLs are `/media/<key>`.
nginx serves `location /media/` straight off disk (`deploy/nginx.conf`) —
those requests never reach the API. Injected via `Depends(get_media_storage)`.

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

### Practice & grading (`app/practice/`)
`Question.answer_schema` is JSON that always contains the correct answer, keyed
by `Question.type` (`mcq_single` / `mcq_multi` / `numeric`). Two pure modules
keep it server-side: `grading.py` (`is_correct(type, answer_schema, submitted)`
— malformed answers grade false, unknown type raises; numeric compares within
`tolerance` with a float-edge guard) and `payload.py` (`public_question()` — the
**single chokepoint** that strips everything but body/difficulty/skill-tags and
MCQ option id+text). `app/routers/practice.py` orchestrates: `POST
/practice/sessions` returns a Topic's ordered questions via `public_question`;
`POST /practice/questions/{id}/submit` grades and writes a `QuestionAttempt`
(`attempt_no` counts prior graded rows + 1); `POST
/practice/questions/{id}/show-solution` sets `solution_viewed` on the latest
attempt, or writes a marker row (`attempt_no = 0`) if there's no submission yet.
Draft-topic questions are 404 to students, visible to a `ContentAdmin`.

### MentisQ guided exchange (`app/mentisq/`)
The AI tutor, structured as a reusable core the thin router wraps:
- `llm_client.py` — the OpenRouter boundary (30s timeout, key from
  `OPENROUTER_API_KEY`, never the DB). Raises `LLMError` / `LLMTimeoutError`.
- `prompt.py` — the guided-mode system prompt is a **versioned template file**
  (`prompts/guided_v1.md`, `GUIDED_PROMPT_VERSION`): no final answer on the first
  reply, full worked solution only on explicit request, name the wrong step in
  shared work, stay in maths, render maths as LaTeX. When launched from a Topic
  or Question, that context (statement, correct answer, worked solution) is
  injected into the `{context}` slot and **never** returned verbatim.
- `settings.py` — `MentisQSettings`: typed accessors over the `Setting` key/value
  table with in-code defaults for `model_name`, `daily_message_cap`,
  `per_student_monthly_cap_usd` (50), `global_monthly_cap_usd` (nullable).
- `service.py` — `MentisQService.post_message`: before any provider call, checks
  the student's `ok` messages-today against `daily_message_cap`, their
  month-to-date `cost_usd` sum against `per_student_monthly_cap_usd`, and the
  global month sum against `global_monthly_cap_usd` if set; over any → a fixed
  `limit_reached` reply, no LLM call, nothing persisted. A successful exchange
  persists the user + assistant `MentisQMessage`, splitting the provider usage
  across the pair (prompt tokens on the user turn, completion tokens + `cost_usd`
  on the assistant turn) so `SUM(cost_usd)` counts each exchange once. A timeout
  / outage / bad response returns `FALLBACK_MESSAGE`, stores both turns
  `status = failed`, and is metered against nothing (the daily-cap count filters
  to `role = user AND status = ok`). Time comes only from the injected `Clock`
  (UTC day / month windows).

`app/routers/mentisq.py` (`POST /mentisq/messages`) resolves the optional
Topic/Question context and maps the result to `{session_id, reply, status}`.
`app/routers/admin.py` (`GET`/`PUT /admin/mentisq-settings`) is gated by
`require_super_admin` (`ROLE_SUPER_ADMIN`) — every other caller gets 403; a
`null` `global_monthly_cap_usd` in the PUT body clears the ceiling.

### Content seeding (`app/ingest/`)
Course content is authored as repo files under `api/content/`: `manifest.yaml`
describes the Year Level → Subject → Unit → Topic tree (with `order`,
prerequisites by topic slug, and each Topic's questions incl. `answer_schema` +
`worked_solution`), and one Markdown file per Topic under `content/lectures/`
holds the lecture body. `slug` is the stable natural key at every level.

`app/ingest/` is the reusable core, structured as the contract a future admin
upload UI will call — the CLI is only a wrapper:
- `manifest.py` — `parse_manifest(data, lecture_loader=...)` / `load_manifest_file(path)`
  validate structure, question types, `answer_schema` shape, slug uniqueness,
  and prerequisite references, raising `ManifestError` (never a bare
  `ValidationError`) for anything an author can fix. No side effects.
- `ingest.py` — `ingest_manifest(db, manifest)` / `load_and_ingest(db, path)`
  upsert every entity by slug in one transaction; a second run over the same
  input changes and creates nothing (idempotent). Entities dropped from the
  manifest are left in place, not deleted (they may carry attempt/view rows).
- `__main__.py` — `python -m app.ingest [manifest]`.

Run it locally after `alembic upgrade head`; it also runs in `setup-vps.sh` and
the deploy workflow, after migrations.

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
`alembic upgrade head` → `python -m app.ingest` (load repo content) →
`npm install && npm run build` → `systemctl restart math-high-api` + `reload nginx`.

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
