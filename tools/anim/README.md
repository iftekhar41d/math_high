# `tools/anim/` — animation authoring toolchain

Turns a plain-language idea into a **reviewed** explainer animation: an LLM drafts
a [Manim](https://www.manim.community/) scene, the tool renders it, feeds any
render traceback back and retries (bounded), generates a caption transcript, and
hands a human the `.mp4` + `.vtt` to approve or reject. Approved artifacts are
uploaded through the **ContentAdmin animation screen** (Phase 2 ticket 11); the
idea and the final script are committed under `scenes/<slug>/` so the animation
can be re-rendered or hand-edited later.

**This toolchain never runs on the VPS and is never installed into the API venv**
([ADR-0004](../../docs/adr/0004-authoring-time-background-work.md)). A developer or
ContentAdmin runs it locally or in CI. It reuses `OPENROUTER_API_KEY` but reads
its **own** `ANIM_LLM_MODEL`, and it does not touch MentisQ spend or caps.

## Install (developer machine / CI only)

Needs, in addition to the Python deps: a **LaTeX** distribution (TeX Live or
MiKTeX, with `latex` + `dvisvgm` on `PATH`) and **ffmpeg**.

```bash
cd tools/anim
python -m venv .venv && .venv/Scripts/activate   # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                             # fill in OPENROUTER_API_KEY; set ANIM_LLM_MODEL
```

`.env` is gitignored. You can also just export `OPENROUTER_API_KEY` /
`ANIM_LLM_MODEL` in your shell — exported vars always win over `.env`.

## Use

Run from `tools/anim/` so `import anim` resolves.

```bash
# draft -> render (with retries) -> transcript -> interactive review
python author.py --slug adding-fractions \
  --idea "Show why 1/2 + 1/3 = 5/6 by rewriting both as sixths on a bar model."

# idea too long for a flag? put it in a file
python author.py --slug adding-fractions --idea-file my-idea.txt

# reviewer rejected an earlier run — regenerate from the committed script + a note
python author.py --slug adding-fractions --from-scene \
  --reject-note "the bar model is off-screen at the bottom; shrink it and centre it"

# hand-edited scenes/adding-fractions/scene.py — just re-render it, no LLM
python author.py --slug adding-fractions --rerender

# CI / unattended — auto-approve whatever renders
python author.py --slug adding-fractions --idea-file my-idea.txt --yes
```

At the review prompt: **`y`** approve, **`r`** reject and type a note (fed into
the next generation), **`q`** quit. On approval the tool prints the `.mp4` +
`.vtt` paths and a `git add scenes/<slug>/` reminder.

### Settings

| Var / flag | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | — (**required**) | Shared with the API; the toolchain never stores it. |
| `ANIM_LLM_MODEL` | `openai/gpt-4o` | The model that drafts scripts + transcripts. Its own setting — not the API's `OPENROUTER_MODEL`. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | |
| `ANIM_RENDER_RETRIES` / `--retries` | `3` | How many times a render traceback is fed back to the model. |
| `ANIM_RENDER_QUALITY` / `--quality` | `m` | Manim quality: `l` `m` `h` `p` `k`. `m` = 720p30, fine for review. |
| `ANIM_LLM_TIMEOUT_SECONDS` | `120` | Per LLM call. |
| `--max-regenerations` | `3` | Reviewer rejections tolerated before the tool gives up. |
| `--out` | `tools/anim/out/` | Where the `.mp4` + `.vtt` land (gitignored). |

## What gets written where

| Path | Committed? | What |
|---|---|---|
| `scenes/<slug>/idea.txt` | **yes** | the prompt the animation was authored from |
| `scenes/<slug>/scene.py` | **yes** | the final Manim script (rendered / approved) |
| `out/<slug>/<slug>.mp4` | no (gitignored) | the silent render — upload via ticket 11 |
| `out/<slug>/<slug>.vtt` | no (gitignored) | the caption transcript — upload via ticket 11 |
| `out/<slug>/media/` | no (gitignored) | Manim's scratch tree |

Publishing an `Animation` requires a transcript (ticket 10/11), which is why the
`.vtt` is a first-class output, not an afterthought.

## Pipeline

```
idea (text)
  -> LLM drafts a Manim scene script                     anim/scriptgen.py
  -> write idea.txt + scene.py under scenes/<slug>/      anim/scene_store.py
  -> render; on failure feed the traceback back, retry   anim/render.py  (bounded by ANIM_RENDER_RETRIES)
  -> LLM writes captions; laid out as WebVTT             anim/transcript.py
  -> human reviewer approves / rejects                   anim/pipeline.py  (reviewer injected)
       approve -> artifacts ready to upload
       reject  -> regenerate with the note, re-render, re-review  (bounded by --max-regenerations)
```

`anim/pipeline.py::author_animation` is the orchestrator; the reviewer is an
injected `ReviewRequest -> ReviewDecision` callable (the CLI prompts a human, the
smoke test stubs it). Nothing here writes to the app DB or the media store — the
ContentAdmin screen owns the upload.

**Correctness is the reviewer's job.** v1 has no automated maths check (the CAS
module is deliberately not a dependency). TTS voiceover and shared asset
libraries are deferred.

## Smoke test (outside `pytest`)

```bash
cd tools/anim && python smoke_test.py
```

Imports every module (proving the package loads with **no Manim installed**),
exercises the pure seams (`scene_name_for`, `extract_scene_code`,
`parse_caption_lines`, `to_vtt`, slug validation), and runs the full pipeline
against a stubbed LLM and a stubbed renderer — including render-failure retry,
retry exhaustion, and reject-then-regenerate. Needs only `httpx`. The API's
`pytest` suite does **not** run or depend on this.

CI can run it as its own job:

```bash
pip install httpx && cd tools/anim && python smoke_test.py
```
