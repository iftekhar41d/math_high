"""The guided-mode prompt renderer — a pure seam, no DB or HTTP."""

from __future__ import annotations

from app.mentisq.prompt import PromptContext, build_prompt, render_system_prompt


def test_system_prompt_carries_the_guided_rules_and_no_context_block():
    prompt = render_system_prompt(None)
    assert "never simply hand" in prompt or "never" in prompt
    assert "LaTeX" in prompt
    # Nothing left where the context slot was.
    assert "{context}" not in prompt
    assert "Problem context" not in prompt


def test_empty_context_renders_no_context_block():
    assert "Problem context" not in render_system_prompt(PromptContext())


def test_context_is_injected_when_present():
    prompt = render_system_prompt(
        PromptContext(
            topic_title="Integers",
            question_body="What is -3 + 5?",
            correct_answer="b) 2",
            worked_solution="Count up from -3.",
        )
    )
    assert "Problem context" in prompt
    assert "Integers" in prompt
    assert "b) 2" in prompt
    assert "Count up from -3." in prompt


def test_build_prompt_appends_the_student_message():
    full = build_prompt("  Why is it 2?  ", None)
    assert full.rstrip().endswith("Student: Why is it 2?")
