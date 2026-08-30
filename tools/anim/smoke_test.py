#!/usr/bin/env python
"""Lightweight smoke test for the authoring toolchain — runs OUTSIDE `pytest`.

    cd tools/anim && python smoke_test.py

Covers import + the pure seams + the pipeline with a stubbed LLM and a stubbed
renderer. It deliberately does NOT install or invoke Manim/LaTeX/ffmpeg, so it is
safe to run anywhere and the API's `pytest` suite never depends on this package.
Exits non-zero on the first failure; prints `ok: N checks` on success.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_checks = 0
_failures: list[str] = []


def check(label: str, cond: bool) -> None:
    global _checks
    _checks += 1
    if cond:
        print(f"  ok  {label}")
    else:
        _failures.append(label)
        print(f"FAIL  {label}")


def section(name: str) -> None:
    print(f"\n# {name}")


def raised(fn, exc) -> bool:
    try:
        fn()
        return False
    except exc:
        return True


# --------------------------------------------------------------------------- #
# imports — every module must import with no Manim installed
# --------------------------------------------------------------------------- #
section("imports")
from anim import (  # noqa: E402
    config,
    llm,
    pipeline,
    prompt,
    render,
    scene_store,
    scriptgen,
    transcript,
)

check("all submodules import", all([config, llm, prompt, scriptgen, render, transcript, scene_store, pipeline]))
check("render imports without `manim` present", "manim" not in sys.modules)


# --------------------------------------------------------------------------- #
# scriptgen pure seams
# --------------------------------------------------------------------------- #
section("scriptgen")
check("scene_name_for kebab -> PascalCase+Scene", scriptgen.scene_name_for("adding-fractions") == "AddingFractionsScene")
check("scene_name_for leading digit is fixed", scriptgen.scene_name_for("2d-shapes")[0].isalpha())
check("scene_name_for already-Scene not doubled", scriptgen.scene_name_for("intro-scene") == "IntroScene")

_FENCED = """Sure! Here is the animation:

```python
from manim import *


class DemoScene(Scene):
    def construct(self):
        self.add(Text("hi"))
        self.wait(1)
```

Let me know if you want changes.
"""
extracted = scriptgen.extract_scene_code(_FENCED)
check("extract_scene_code pulls the fence", extracted.startswith("from manim import *"))
check("extract_scene_code drops the prose", "Let me know" not in extracted)
check("extract_scene_code ends with newline", extracted.endswith("\n"))

_UNFENCED = "from manim import *\n\nclass BareScene(Scene):\n    def construct(self):\n        self.wait(1)\n"
check("extract_scene_code accepts a bare script", scriptgen.extract_scene_code(_UNFENCED).strip().endswith("self.wait(1)"))

try:
    scriptgen.extract_scene_code("I can't help with that.")
    check("extract_scene_code rejects non-script", False)
except scriptgen.ScriptGenerationError:
    check("extract_scene_code rejects non-script", True)


# --------------------------------------------------------------------------- #
# transcript pure seams
# --------------------------------------------------------------------------- #
section("transcript")
lines = transcript.parse_caption_lines("1. First we look at halves.\n2) Then thirds.\n- A common denominator.\n\n")
check("parse_caption_lines strips markers", lines == ["First we look at halves.", "Then thirds.", "A common denominator."])

vtt = transcript.to_vtt(["one", "two", "three"], duration_seconds=30.0)
check("to_vtt starts WEBVTT", vtt.startswith("WEBVTT\n"))
check("to_vtt has one cue per line", vtt.count("-->") == 3)
check("to_vtt final cue ends at duration", "00:00:30.000" in vtt)
check("to_vtt first cue starts at zero", "00:00:00.000 -->" in vtt)

vtt_nodur = transcript.to_vtt(["a", "b"], duration_seconds=None)
check("to_vtt tolerates unknown duration", vtt_nodur.count("-->") == 2 and vtt_nodur.startswith("WEBVTT"))

try:
    transcript.parse_caption_lines("   \n\n")
    check("parse_caption_lines rejects empty", False)
except transcript.TranscriptError:
    check("parse_caption_lines rejects empty", True)


# --------------------------------------------------------------------------- #
# scene_store round-trip (into a temp dir, not the real scenes/)
# --------------------------------------------------------------------------- #
section("scene_store")
check("validate_slug rejects spaces", raised(lambda: scene_store.validate_slug("bad slug"), scene_store.SceneStoreError))
check("validate_slug accepts kebab", scene_store.validate_slug("adding-fractions") == "adding-fractions")
check("validate_slug rejects CamelCase", raised(lambda: scene_store.validate_slug("AddingFractions"), scene_store.SceneStoreError))

with tempfile.TemporaryDirectory() as tmp:
    scene_store.SCENES_DIR = Path(tmp)  # redirect writes
    saved = scene_store.save("demo-anim", idea="show 1/2 + 1/3", script="from manim import *\nclass X(Scene):\n    pass")
    check("save writes idea.txt", saved.idea_path.read_text().strip() == "show 1/2 + 1/3")
    check("save writes scene.py", saved.script_path.is_file())
    check("exists() true after save", scene_store.exists("demo-anim"))
    loaded = scene_store.load("demo-anim")
    check("load round-trips the script", "class X(Scene)" in loaded.script)
    check("load round-trips the idea", loaded.idea.strip() == "show 1/2 + 1/3")


# --------------------------------------------------------------------------- #
# scriptgen + LLM stub
# --------------------------------------------------------------------------- #
section("scriptgen <- stub LLM")

_SCRIPT_REPLY = "```python\nfrom manim import *\n\n\nclass FooScene(Scene):\n    def construct(self):\n        self.wait(1)\n```"
_CAPTIONS_REPLY = "1. Look at the fraction.\n2. Add the parts.\n3. Simplify."


class StubLLM:
    """Returns a script for the script prompt, captions for the transcript
    prompt. Records every call."""

    def __init__(self):
        self.calls: list[list[dict]] = []
        self.script_replies: list[str] = []

    def complete(self, *, messages, model):
        self.calls.append(messages)
        system = messages[0]["content"]
        if system == prompt.TRANSCRIPT_SYSTEM:
            return _CAPTIONS_REPLY
        if self.script_replies:
            return self.script_replies.pop(0)
        return _SCRIPT_REPLY


cfg = config.Config(
    openrouter_api_key="test-key",
    model="test/model",
    base_url="https://example.invalid",
    render_retries=2,
    render_quality="l",
    llm_timeout_seconds=5.0,
)

stub = StubLLM()
script = scriptgen.generate_scene_script(stub, cfg, idea="fractions", scene_name="FooScene")
check("generate_scene_script returns runnable code", "class FooScene(Scene)" in script)
check("generate_scene_script sent the SCRIPT_SYSTEM prompt", stub.calls[0][0]["content"] == prompt.SCRIPT_SYSTEM)
check("generate_scene_script sent the configured model", "fractions" in stub.calls[0][1]["content"])

stub2 = StubLLM()
scriptgen.generate_scene_script(
    stub2, cfg, idea="fractions", scene_name="FooScene",
    previous_script="old code", render_traceback="NameError: name 'Circle2' is not defined",
)
check("retry prompt carries the traceback", "NameError" in stub2.calls[0][1]["content"])
check("retry prompt carries the previous script", "old code" in stub2.calls[0][1]["content"])


# --------------------------------------------------------------------------- #
# pipeline with stub LLM + stub renderer
# --------------------------------------------------------------------------- #
section("pipeline <- stub LLM + stub renderer")

_real_render = pipeline.render_scene
_real_probe = pipeline.probe_duration_seconds


def _fake_probe(_path):
    return 20.0


def make_fake_render(fail_times: int):
    state = {"n": 0}

    def _fake_render(script_path, scene_name, *, out_dir, quality, timeout_seconds=600.0):
        state["n"] += 1
        if state["n"] <= fail_times:
            return render.RenderResult(ok=False, video_path=None, log="boom", traceback="ValueError: bad mobject")
        vid = Path(out_dir) / "media" / "fake.mp4"
        vid.parent.mkdir(parents=True, exist_ok=True)
        vid.write_bytes(b"\x00\x00\x00 ftypmp42fake")
        return render.RenderResult(ok=True, video_path=vid, log="done", traceback=None)

    return _fake_render


pipeline.probe_duration_seconds = _fake_probe

try:
    # (a) clean render, reviewer approves first time
    with tempfile.TemporaryDirectory() as tmp:
        scene_store.SCENES_DIR = Path(tmp) / "scenes"
        pipeline.render_scene = make_fake_render(fail_times=0)
        approvals: list[int] = []

        def approve(req):
            approvals.append(req.generation)
            return pipeline.ReviewDecision(approved=True)

        art = pipeline.author_animation(
            StubLLM(), cfg, idea="add fractions", slug="demo-a",
            out_dir=Path(tmp) / "out", reviewer=approve, max_regenerations=2,
        )
        check("pipeline: mp4 produced", art.video_path.is_file())
        check("pipeline: vtt produced", art.transcript_path.is_file() and art.transcript_path.read_text().startswith("WEBVTT"))
        check("pipeline: scene.py committed", (Path(tmp) / "scenes" / "demo-a" / "scene.py").is_file())
        check("pipeline: idea.txt committed", (Path(tmp) / "scenes" / "demo-a" / "idea.txt").read_text().strip() == "add fractions")
        check("pipeline: approved on first generation", art.generations == 1 and approvals == [1])
        check("pipeline: one render attempt", art.render_attempts == 1)
        check("pipeline: mp4 is slug-named", art.video_path.name == "demo-a.mp4")

        # a second slug into the SAME out_dir must not collide with the first
        art2 = pipeline.author_animation(
            StubLLM(), cfg, idea="other", slug="demo-a2",
            out_dir=Path(tmp) / "out",
            reviewer=lambda r: pipeline.ReviewDecision(approved=True),
        )
        check(
            "pipeline: two slugs share out_dir without collision",
            art.video_path.is_file() and art2.video_path.is_file()
            and art.video_path != art2.video_path
            and art2.video_path.parent == (Path(tmp) / "out" / "demo-a2"),
        )

    # (b) render fails twice then succeeds — traceback fed back, bounded retry
    with tempfile.TemporaryDirectory() as tmp:
        scene_store.SCENES_DIR = Path(tmp) / "scenes"
        pipeline.render_scene = make_fake_render(fail_times=2)
        llm_b = StubLLM()
        art = pipeline.author_animation(
            llm_b, cfg, idea="x", slug="demo-b",
            out_dir=Path(tmp) / "out",
            reviewer=lambda r: pipeline.ReviewDecision(approved=True),
            max_regenerations=1,
        )
        check("pipeline: 3 render attempts after 2 failures", art.render_attempts == 3)
        script_calls = [c for c in llm_b.calls if c[0]["content"] == prompt.SCRIPT_SYSTEM]
        check("pipeline: LLM re-drafted twice on failure", len(script_calls) == 3)
        check("pipeline: a redraft carried the traceback", any("ValueError: bad mobject" in c[1]["content"] for c in script_calls))

    # (c) render keeps failing past the bound -> PipelineError
    with tempfile.TemporaryDirectory() as tmp:
        scene_store.SCENES_DIR = Path(tmp) / "scenes"
        pipeline.render_scene = make_fake_render(fail_times=99)
        check(
            "pipeline: exhausted retries raise PipelineError",
            raised(
                lambda: pipeline.author_animation(
                    StubLLM(), cfg, idea="x", slug="demo-c",
                    out_dir=Path(tmp) / "out",
                    reviewer=lambda r: pipeline.ReviewDecision(approved=True),
                    max_regenerations=0,
                ),
                pipeline.PipelineError,
            ),
        )

    # (d) reviewer rejects once with a note, then approves -> regeneration
    with tempfile.TemporaryDirectory() as tmp:
        scene_store.SCENES_DIR = Path(tmp) / "scenes"
        pipeline.render_scene = make_fake_render(fail_times=0)
        llm_d = StubLLM()
        seen: list[int] = []

        def reject_then_approve(req):
            seen.append(req.generation)
            if req.generation == 1:
                return pipeline.ReviewDecision(approved=False, note="make the title bigger")
            return pipeline.ReviewDecision(approved=True)

        art = pipeline.author_animation(
            llm_d, cfg, idea="x", slug="demo-d",
            out_dir=Path(tmp) / "out", reviewer=reject_then_approve, max_regenerations=3,
        )
        check("pipeline: regenerated after rejection", art.generations == 2 and seen == [1, 2])
        script_calls_d = [c for c in llm_d.calls if c[0]["content"] == prompt.SCRIPT_SYSTEM]
        check("pipeline: rejection note fed into the redraft", any("make the title bigger" in c[1]["content"] for c in script_calls_d))

    # (e) reviewer never satisfied -> PipelineError after the bound
    with tempfile.TemporaryDirectory() as tmp:
        scene_store.SCENES_DIR = Path(tmp) / "scenes"
        pipeline.render_scene = make_fake_render(fail_times=0)
        check(
            "pipeline: endless rejection raises PipelineError",
            raised(
                lambda: pipeline.author_animation(
                    StubLLM(), cfg, idea="x", slug="demo-e",
                    out_dir=Path(tmp) / "out",
                    reviewer=lambda r: pipeline.ReviewDecision(approved=False, note="no"),
                    max_regenerations=1,
                ),
                pipeline.PipelineError,
            ),
        )
finally:
    pipeline.render_scene = _real_render
    pipeline.probe_duration_seconds = _real_probe


# --------------------------------------------------------------------------- #
section("result")
if _failures:
    print(f"\n{len(_failures)} / {_checks} checks FAILED:")
    for f in _failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"\nok: {_checks} checks")
