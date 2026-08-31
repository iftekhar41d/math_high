# Creating an animation

Step-by-step guide to turning a plain-language idea into a reviewed explainer
animation using the **`tools/anim/`** toolchain, then getting it in front of
students.

The toolchain: an LLM drafts a [Manim](https://www.manim.community/) scene → the
tool renders it → any render error is fed back to the model and retried
(bounded) → the LLM writes captions as a `.vtt` → **a human approves or rejects**
→ you upload the approved `.mp4` + `.vtt` through the ContentAdmin **Animations**
screen and attach it to one or more Topics.

> **Where it runs:** only on a developer / ContentAdmin machine (or CI). It is
> **never** installed into the API venv and **never** runs on the VPS
> ([ADR-0004](docs/adr/0004-authoring-time-background-work.md)). Rendering is
> heavy; the running service only ever handles the finished file.

---

## What the tool does and does *not* know

| The tool knows | The tool does **not** know |
|---|---|
| a **slug** (an id you pick) | which Topic the animation is for |
| an **idea** (free text — this is the only place the subject matter comes from) | anything about the course tree, Year 7 units, etc. |

Topic linkage happens later, entirely in the **Animations** admin screen
(step 6). One rendered animation can be attached to several Topics.

### What is a slug?

A short, filename-safe id: lowercase letters and digits, words joined by single
hyphens. Enforced pattern: `^[a-z0-9]+(?:-[a-z0-9]+)*$`.

It is the animation's **own** key (not the topic). It names the committed folder
`tools/anim/scenes/<slug>/`, the output folder `tools/anim/out/<slug>/`, derives
the Manim class name (`adding-fractions` → `class AddingFractions(Scene)`), and
keys the `Animation` row in the DB — re-uploading the same slug **updates** that
row instead of creating a new one.

Example values: `adding-fractions`, `number-line`, `pythagoras-intro`,
`solving-two-step-equations`, `angles-on-a-straight-line`.

---

## Prerequisites (one time, per machine)

Install these and make sure they are on `PATH`:

1. **Python 3.11+**
2. **A LaTeX distribution** — MiKTeX (Windows) or TeX Live (macOS/Linux), with
   `latex` and `dvisvgm` callable.
3. **ffmpeg**
4. **An OpenRouter API key** — the same value as `api/.env`'s `OPENROUTER_API_KEY`.

Quick check:

```powershell
python --version
latex --version
dvisvgm --version
ffmpeg -version
```

If LaTeX or ffmpeg is missing, the render step fails with a clear message — install
what it names rather than guessing.

---

## Step 1 — Set up the toolchain venv (one time)

Run from `tools/anim/`. This venv is **separate** from `api/.venv`.

**Windows (PowerShell):**

```powershell
cd tools\anim
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
cd tools/anim
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` here is just `manim`, `httpx`, `python-dotenv` — Manim is
**not** in the API's requirements.

---

## Step 2 — Configure environment

Copy the example env file and fill it in (it is gitignored):

```powershell
cp .env.example .env
```

Edit `tools/anim/.env`:

```ini
# Reuse the API's OpenRouter key (same value as api/.env)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# This tool's OWN model — distinct from the API's OPENROUTER_MODEL.
# Use a capable code model; gpt-4o-mini often produces scripts that will not render.
ANIM_LLM_MODEL=openai/gpt-4o
```

You can instead just `export` / `$env:` these in your shell — exported vars
always win over `.env`.

Authoring cost is billed under `ANIM_LLM_MODEL` and never touches MentisQ student
spend or caps.

---

## Step 3 — Write the idea

Decide:

- **slug** — e.g. `adding-fractions`
- **idea** — a plain-language description of what the animation should *show* and
  *teach*, Year 7 Mathematics (NSW). Be concrete about the visual.

Short idea → pass it inline with `--idea`. More than a sentence or two → put it in
a file and use `--idea-file`.

Example `my-idea.txt`:

```
Show why 1/2 + 1/3 = 5/6 by rewriting both fractions as sixths on a bar model.
Start with two bars, one split in halves and one in thirds. Re-split each into
sixths, shade 3/6 and 2/6, then combine to 5/6. Keep it under 30 seconds.
```

---

## Step 4 — Run the author

From `tools/anim/` with the venv active:

```powershell
python author.py --slug adding-fractions --idea "Show why 1/2 + 1/3 = 5/6 on a bar model."
```

or with a file:

```powershell
python author.py --slug adding-fractions --idea-file my-idea.txt
```

What happens:

1. The LLM drafts a single-file Manim scene.
2. `scenes/<slug>/idea.txt` and `scenes/<slug>/scene.py` are written.
3. The tool shells out to `manim render`. **On a render failure the traceback is
   fed back to the model and it retries**, up to `--retries` (default 3).
4. The LLM writes caption lines; they are laid out as WebVTT.
5. The tool prints a **review prompt**.

---

## Step 5 — Review (the human gate)

The tool prints the paths and asks:

```
Approve? [y]es / [r]eject+note / [q]uit:
```

- **`y`** — approve. The tool prints the final artifact paths and a
  `git add` reminder.
- **`r`** — reject, then type a note (e.g. *"the bar model runs off the bottom of
  the frame — shrink it and centre it"*). The note is fed into the next
  generation, which re-renders and re-prompts. Bounded by `--max-regenerations`
  (default 3).
- **`q`** — quit without approving.

**You own mathematical and pedagogical correctness at this gate** — there is no
automated maths check in v1. Actually open the `.mp4` before answering.

### Outputs on approval

| Path | Committed? | What |
|---|---|---|
| `tools/anim/scenes/<slug>/idea.txt` | **yes** | the idea it was authored from |
| `tools/anim/scenes/<slug>/scene.py` | **yes** | the final Manim script |
| `tools/anim/out/<slug>/<slug>.mp4` | no (gitignored) | the silent render — upload this |
| `tools/anim/out/<slug>/<slug>.vtt` | no (gitignored) | the caption transcript — upload this |

Commit the source so the render is reproducible:

```powershell
git add tools/anim/scenes/adding-fractions/
git commit -m "Animation: adding-fractions scene"
```

---

## Step 6 — Upload and attach to a Topic

The toolchain does **not** touch the app DB or media store. Get the animation to
students through the admin screen:

1. Log in as a **ContentAdmin** and open **Animations** (`/admin/animations`).
   (In dev, `ifti1621@yahoo.com` is a `content_admin`.)
2. Click **+ New animation** (or pick an existing row to update it).
3. Fill in:
   - **Slug** — same slug you used in the tool (upsert-by-slug; locked after
     creation).
   - **Title**, **Description**, **Duration (seconds)**.
   - **Video** — choose `out/<slug>/<slug>.mp4` (required when creating).
   - **Transcript (VTT)** — choose `out/<slug>/<slug>.vtt` (optional to save,
     **required before publishing**).
   - **Attached topics** — tick one or more Topics.
4. **Save.**
5. In the **Preview** panel, watch the draft, then **Publish**. Publishing is
   blocked with a 409 until a transcript is attached.

Students then see it in the **Animations** section on that Topic's lecture page.
Drafts are visible to ContentAdmins only.

---

## Other entry points

Run all of these from `tools/anim/` with the venv active.

```powershell
# Regenerate from the committed script + a fix note (previous run rejected)
python author.py --slug adding-fractions --from-scene ^
  --reject-note "the denominators overlap the title — move them down"

# You hand-edited scenes/adding-fractions/scene.py — just re-render, no LLM call
python author.py --slug adding-fractions --rerender

# Unattended / CI — auto-approve whatever renders
python author.py --slug adding-fractions --idea-file my-idea.txt --yes
```

`--rerender` does not call the LLM and leaves the existing `.vtt` untouched.

---

## Settings reference

| Var / flag | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | — (**required**) | Shared with the API; never stored by the tool. |
| `ANIM_LLM_MODEL` | `openai/gpt-4o` | Model that drafts scripts + transcripts. Its own setting. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | |
| `ANIM_RENDER_RETRIES` / `--retries` | `3` | How many times a render traceback is fed back to the model. |
| `ANIM_RENDER_QUALITY` / `--quality` | `m` | Manim quality: `l` `m` `h` `p` `k`. `m` = 720p30, fine for review. |
| `ANIM_LLM_TIMEOUT_SECONDS` | `120` | Per LLM call. |
| `--max-regenerations` | `3` | Reviewer rejections tolerated before the tool gives up. |
| `--scene-name` | derived from slug | Override the Manim `Scene` subclass name. |
| `--out` | `tools/anim/out/` | Where the `.mp4` + `.vtt` land (gitignored). |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `config error: OPENROUTER_API_KEY is not set` | Export it or put it in `tools/anim/.env`. |
| `RenderUnavailable` / `manim: command not found` | The venv isn't active, or Manim didn't install. Re-run `pip install -r requirements.txt` in `tools/anim/.venv`. |
| Render fails on LaTeX (`latex`/`dvisvgm` errors) | Install MiKTeX / TeX Live and ensure `latex` + `dvisvgm` are on `PATH`. |
| Render fails on ffmpeg | Install ffmpeg and put it on `PATH`. |
| Every generation fails to render after retries | Try a stronger `ANIM_LLM_MODEL`; `gpt-4o-mini` often produces scripts that won't render. Or hand-edit `scenes/<slug>/scene.py` and `--rerender`. |
| Publish button returns 409 | Upload a `.vtt` transcript and Save first — a transcript is required to publish. |
| Want to check the toolchain without Manim/LaTeX/ffmpeg | `cd tools/anim && python smoke_test.py` (runs outside `pytest`). |

---

## Pipeline at a glance

```
idea (text)
  -> LLM drafts a Manim scene script                     anim/scriptgen.py
  -> write idea.txt + scene.py under scenes/<slug>/      anim/scene_store.py
  -> render; on failure feed the traceback back, retry   anim/render.py   (bounded by ANIM_RENDER_RETRIES)
  -> LLM writes captions; laid out as WebVTT             anim/transcript.py
  -> human reviewer approves / rejects                   anim/pipeline.py
       approve -> .mp4 + .vtt ready to upload
       reject  -> regenerate with the note, re-render, re-review  (bounded by --max-regenerations)
  -> ContentAdmin screen: upload, attach Topics, publish
```

Full reference: [`tools/anim/README.md`](tools/anim/README.md). Repo skill:
[`.claude/skills/author-animation/SKILL.md`](.claude/skills/author-animation/SKILL.md).
