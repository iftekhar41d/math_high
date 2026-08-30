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
cp .env.example .env                              # then fill in OPENROUTER_API_KEY / OPENROUTER_MODEL
alembic upgrade head                              # build the schema (creates data/app.db)
python -m app.ingest                              # load pilot course content (idempotent)
uvicorn app.main:app --reload --env-file .env     # http://localhost:8000, docs at /docs
```

`api/.env` is gitignored and loaded by uvicorn's `--env-file`. The only vars
MentisQ needs are `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` (the model id,
e.g. `openai/gpt-4o-mini`); everything else has a working default. In prod these
live in `/etc/math-high-api.env`, loaded by the systemd unit.

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
OpenRouter; 30s timeout; **key and model name from the environment**
(`OPENROUTER_API_KEY` / `OPENROUTER_MODEL`), never the DB). Override
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
by `Question.type` (`mcq_single` / `mcq_multi` / `numeric` / `symbolic` /
`multi_part`). Two pure modules keep it server-side: `grading.py`
(`is_correct(type, answer_schema, submitted)` — malformed answers grade false,
unknown type raises; numeric compares within `tolerance` with a float-edge
guard; `symbolic` defers to `app/cas/` for equivalence, never a string match;
`multi_part` bundles sub-questions each graded by the existing per-type grader
and is correct only when every part is — `grade_parts()` returns the ordered
per-part vector the router persists on `QuestionAttempt.part_results`) and
`payload.py` (`public_question()` — the **single chokepoint** that strips
everything but body/difficulty/skill-tags and MCQ option id+text, recursing into
every `multi_part` part). `app/routers/practice.py` orchestrates: `POST
/practice/sessions` persists a `PracticeSession` (`mode = topic`,
`scope_type = topic`), freezes the Topic's ordered questions into
`practice_session_questions`, and returns them via `public_question` (the
response is unchanged — the session is server-side bookkeeping);
`POST /practice/questions/{id}/submit` grades and writes a `QuestionAttempt`
(`attempt_no` counts prior graded rows + 1), linked via
`practice_session_id` to the caller's most recent still-open session that froze
the question (null = standalone attempt); `POST
/practice/questions/{id}/show-solution` sets `solution_viewed` on the latest
attempt, or writes a marker row (`attempt_no = 0`, linked the same way) if
there's no submission yet. `PracticeSession` also carries
`time_limit_seconds` / `submitted_at` / `score`, unused by `topic` mode.
Draft-topic questions are 404 to students, visible to a `ContentAdmin`.
`submit` only returns `worked_solution` once `attempt_no` reaches the
`practice.solution_reveal_after_attempts` `Setting` (`app/practice/settings.py`,
default 1 — from the first submission on); the explicit `show-solution` request
is never gated by it.

**Timed quiz mode** (`mode = timed`, `scope_type = unit`) builds on the same
tables plus a third pure module, `timed.py` — `Countdown(time_limit_seconds,
started_at)` (`.remaining(now)` / `.is_after_limit(now)`) and
`proportion_correct(...)`, no DB or clock. `POST /practice/timed-sessions`
(`{unit_id}`) freezes every question the caller may practise in the Unit (topic
order, then seed order), sets `time_limit_seconds` to the sum of the questions'
`estimated_time_seconds` (a null filled with the `practice.default_question_seconds`
`Setting`, default 90), and stamps `started_at` from the `Clock`. Expiry is
**server-authoritative**: `remaining_seconds` is derived from `started_at` + the
`Clock`, and `GET /practice/sessions/{id}` on a run whose countdown has run out
**closes it** (scores + stamps `submitted_at`) before responding — so an
abandoned tab still yields a review (mutating GET, like
`GET /content/topics/{slug}` writing a `TopicView`). While the session is open a
`submit` is graded and persisted as normal but the response withholds
`is_correct` / `worked_solution` (returned `null`); an answer past the limit is
stored with `QuestionAttempt.after_time_limit = True`, never rejected. The
withholding (and the 409 from `show-solution`) keys off
`_open_timed_session_for(user, question)` — the caller's newest open timed run
that froze the question, independent of `_active_session_id`, so a topic run
started afterwards can't defeat it; it lapses `_TIMED_ABANDON_GRACE` (15 min)
past the limit so a stale never-closed run doesn't block ordinary topic
practice. A running timed quiz also owns the `practice_session_id` of every
submit of a question it froze. `POST /practice/sessions/{id}/submit` (timed
only, idempotent) scores the frozen set (unanswered → incorrect), sets `score` /
`submitted_at`, and returns the review — per-question correctness + worked
solutions. `GET` returns the open quiz (public questions + `remaining_seconds` +
answers so far, for reload-resume) or, once submitted, the review. Each start is
a new `PracticeSession`; retakes are unlimited.

**Mixed practice mode** (`mode = mixed`, `scope_type = unit` | `year_level`)
adds a fourth pure module, `mixed.py` — `select_mixed_questions(candidates, *,
skill_mastery, question_count, rng)` returning the ordered ids to freeze, no DB
/ clock (deterministic given its seeded `rng`). `POST /practice/mixed-sessions`
(`{scope_type, scope_id, question_count?}`) gathers every question the caller
may practise in the scope, reads their `PerformanceSnapshot` rows
(`dimension = skill_tag`) **for the scope's SkillTags only** into a
`skill_tag_id → mastery` map, and samples the set **once at creation** (no
within-session adaptation). With ≥ 1 in-scope snapshot the draw is weighted
(each SkillTag weight `1 - mastery`, floored at `0.05`; a question's weight is
the mean of its tags'; Efraimidis–Spirakis without replacement); with none —
including a student with history in other Units but not this one — it falls back
to even round-robin SkillTag coverage.
Either way the frozen set is ordered difficulty-ascending. `question_count`
defaults to `DEFAULT_MIXED_QUESTION_COUNT` (10, a named constant in `mixed.py`)
and a scope with fewer eligible questions yields a smaller set. Feedback is
**not** withheld — `mixed` is not `timed`, so `_open_timed_session_for` never
matches it and `submit` / `show-solution` behave exactly as for `topic`
practice, with `_active_session_id` linking each attempt to the open mixed run.
`time_limit_seconds` / `submitted_at` / `score` stay null. Each start is a new
`PracticeSession`; no migration (the `mixed` / `year_level` constants already
existed). SPA: `web/src/views/MixedPracticeView.vue` + route
`learn-mixed-practice` (`/learn/units/:unitId/mixed-practice`), reached from a
CTA on the unit's topic list in `BrowseView.vue`.

### CAS equivalence (`app/cas/`)
A pure module in the mould of `grading.py` — no DB, no clock, no network, no
injectable seam (SymPy is deterministic and offline; `sympy` is the one new
`requirements.txt` entry — Manim is **not** here, it lives only in
`tools/anim/`). `check_equivalence(expr_a, expr_b, *, variables=[...],
domain="real"|"positive"|"complex")` parses two expression **strings** and
returns an `EquivalenceResult`: an `outcome` of `EquivalenceOutcome.{EQUIVALENT,
NOT_EQUIVALENT, PARSE_ERROR}` plus a short `detail`. Parsing accepts student
notation (`2(x+1)`, `^` for power) and screens out non-mathematical syntax (a
char whitelist, no `__`, a length cap) before SymPy runs — but junk that still
tokenises (`x y z` → `x*y*z`) lands on `NOT_EQUIVALENT`, not `PARSE_ERROR`.
Either side unparseable → `PARSE_ERROR`; a SymPy blow-up or an undecidable
comparison on parsed input → `NOT_EQUIVALENT` — the module never raises on
expression input. `domain` is caller config, so an unknown value **does** raise
(like `grading`'s unknown question type). The result is truthy iff equivalent
(`bool(check_equivalence(...))`), with `.parsed` separating "wrong" from
"couldn't read it". `expression_parses(text, *, variables, domain)` is the
companion used at author time (`app/ingest/`) to reject a malformed `symbolic`
answer before it reaches a grader. The `symbolic` question grader
(`app/practice/grading.py`) and the MentisQ step-check are the callers.

### Analytics recompute (`app/analytics/`)
An out-of-band job that turns stored `QuestionAttempt` / `TopicView` history
into cached `PerformanceSnapshot` rows (one per (user, `dimension`,
`dimension_id`), `dimension` = `topic` | `skill_tag`). Nothing on the request
path writes there. Reusable core, thin CLI:
- `mastery.py` — pure maths. `mastery` is an exponentially time-weighted
  proportion correct over the **first** graded attempt of each Question (weight
  `0.5 ** (age_days / half_life)`, half-life from the
  `analytics.mastery_half_life_days` `Setting`, default 14). A solution viewed
  *before* the first submission forces that Question incorrect; `mentisq_used`
  is ignored. `trend` is the bucketed sign of (mastery over the last 30 days −
  mastery over the prior 30), same weighting as the headline figure, with a dead
  zone for `flat`.
- `settings.py` — `AnalyticsSettings`: typed access to the half-life and the
  `analytics.recompute_watermark` (ISO instant of the last successful run).
- `recompute.py` — `recompute(db, clock, *, full=False)`: incremental by
  default (only users with a `QuestionAttempt`/`TopicView` after the watermark;
  an empty incremental run writes nothing, watermark untouched), fans each
  first-attempt outcome to its Topic and every SkillTag, upserts snapshots, then
  advances the watermark. `python -m app.analytics.recompute [--full]` is the
  wrapper. A nightly `math-high-snapshots` systemd timer runs it; the deploy
  workflow runs one `--full` backfill after `alembic upgrade head`.

### MentisQ guided exchange (`app/mentisq/`)
The AI tutor — a **multi-turn** guided conversation, structured as a reusable
core the thin router wraps:
- `llm_client.py` — the OpenRouter boundary (30s timeout; `OPENROUTER_API_KEY`
  from the environment, never the DB). `complete(messages=[...], model=...)`
  takes an OpenAI-style message list. Raises `LLMError` / `LLMTimeoutError`.
- `prompt.py` — the guided-mode system prompt is a **versioned template file**
  (`prompts/guided_v2.md`, `GUIDED_PROMPT_VERSION`): no final answer on the first
  assistant turn *of the session*, full worked solution only on explicit request,
  name the wrong step in shared work, stay in maths, render maths as LaTeX. When
  launched from a Topic or Question, that context (statement, correct answer,
  worked solution) is injected into the `{context}` slot and **never** returned
  verbatim. `build_messages(user_message, context, history, *, is_continuation)`
  assembles the wire list: `system` message (ending with a plain statement of
  whether this is the first assistant turn, so the first-reply rule survives
  once early turns leave the window), then `history` (already trimmed /
  failed-filtered by the caller), then the new `user` turn. `HISTORY_MAX_MESSAGES`
  (12) is the replay window — older turns are dropped, not summarised.
- `step_check.py` — a **pure** deterministic algebra check (no DB / clock /
  provider, never raises), the counterpart to `grading.py`. `check_working(text)`
  scans **only the latest student turn** for equality chains — expressions joined
  by `=` on one line (`a = b = c`) or continued across lines by a leading `=`;
  plain adjacent lines are not joined — verifies each consecutive step with
  `app/cas/` `check_equivalence`, and returns a `- step N: VALID` /
  `- step N: INVALID — …` block under a "reference only" header, or `None` when
  nothing checkable parses. A step is only `INVALID` when the two sides differ
  under **every** `app/cas/` domain (`real` / `positive` / `complex`), so a
  restricted-domain identity like `sqrt(x^2) = x` is passed over silently, not
  misreported. A lone `a = b` line (a conditional equation being solved, not an
  identity claim) and any chain with a prose-looking member are skipped — so
  multi-line equation solving goes unchecked (CAS compares expressions, not
  equations, and a false `INVALID` on every written equation would be worse than
  silence). `service.post_message` passes the block to
  `build_messages(..., step_check=...)`, which appends it to the `system`
  message — never a turn of its own, never persisted, adding no provider call.
- `settings.py` — the model name is environment-only (`OPENROUTER_MODEL`, via the
  `model_name()` helper; not stored, not editable at runtime). `MentisQSettings`
  is the runtime-editable caps: typed accessors over the `Setting` key/value
  table with in-code defaults for `daily_message_cap` (2000 — a runaway-loop
  backstop, not a product limit), `per_student_monthly_cap_usd` (50 — the real
  spend guard), `global_monthly_cap_usd` (nullable).
- `service.py` — `MentisQService.post_message`: picks the session
  (`_pick_session` — a matching `session_id` continues that conversation; a
  changed Topic/Question context or `new_chat=True` opens a fresh
  `MentisQSession` stamped with `GUIDED_PROMPT_VERSION`; no `session_id` + no
  context anchor resumes the student's most recent general session). Then, before
  any provider call, checks the student's `ok` messages-today against
  `daily_message_cap`, their month-to-date `cost_usd` sum against
  `per_student_monthly_cap_usd`, and the global month sum against
  `global_monthly_cap_usd` if set; over any → a fixed `limit_reached` reply, no
  LLM call, nothing persisted. Otherwise it sends the system prompt plus the last
  `HISTORY_MAX_MESSAGES` non-`failed` turns of the session. A successful exchange
  persists the user + assistant `MentisQMessage`, splitting the provider usage
  across the pair (prompt tokens on the user turn, completion tokens + `cost_usd`
  on the assistant turn) so `SUM(cost_usd)` counts each exchange once. A timeout
  / outage / bad response returns `FALLBACK_MESSAGE`, stores both turns
  `status = failed`, and is metered against nothing (the daily-cap count filters
  to `role = user AND status = ok`). `set_helpful` records the student's 👍/👎
  (`mentisq_sessions.helpful`, nullable) on one of their own sessions. Time comes
  only from the injected `Clock` (UTC day / month windows).

`app/routers/mentisq.py`: `POST /mentisq/messages` resolves the optional
Topic/Question context, passes `session_id` / `new_chat` through, and maps the
result to `{session_id, reply, status}`; `GET /mentisq/sessions/current` returns
the general conversation the next message would continue (with its non-`failed`
turns) for the SPA to hydrate; `POST /mentisq/sessions/{id}/helpful` sets the
rating (404 if the session isn't the caller's).
`app/routers/admin.py` (`GET`/`PUT /admin/mentisq-settings`) is gated by
`require_super_admin` (`ROLE_SUPER_ADMIN`) — every other caller gets 403. `GET`
also echoes the active `model_name` read-only; `PUT` edits only the caps (a
`null` `global_monthly_cap_usd` clears the ceiling).

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
`python -m app.analytics.recompute --full` (backfill mastery snapshots) →
`npm install && npm run build` → `systemctl restart math-high-api` + `reload nginx`.

The deploy user's sudo is scoped to exactly those two `systemctl` commands. A fresh
VPS is bootstrapped once with `deploy/setup-vps.sh [domain] [repo-url] [app-dir]`
(installs Python/Node/nginx, venv, systemd units incl. the nightly
`math-high-snapshots` timer, nginx site, scoped sudoers rule).
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
