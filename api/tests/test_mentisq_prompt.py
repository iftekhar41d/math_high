"""The guided-mode prompt renderer — a pure seam, no DB or HTTP."""

from __future__ import annotations

from app.mentisq.prompt import (
    GUIDED_PROMPT_VERSION,
    PromptContext,
    build_messages,
    render_system_prompt,
)


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


def test_prompt_version_is_guided_v2():
    assert GUIDED_PROMPT_VERSION == "guided_v2"
    # The v2 rule keys the "no final answer" restriction to the first turn.
    assert "FIRST assistant turn" in render_system_prompt(None)


def test_build_messages_is_system_then_history_then_new_user_turn():

    class T:
        def __init__(self, role, content):
            self.role, self.content = role, content

    history = [T("user", "I got 7"), T("assistant", "Check the sign.")]
    messages = build_messages("  Why is it 2?  ", None, history)

    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[0]["content"].startswith(render_system_prompt(None))
    assert messages[1]["content"] == "I got 7"
    assert messages[-1]["content"] == "Why is it 2?"


def test_build_messages_without_history_is_just_system_and_user():
    messages = build_messages("start", None)
    assert [m["role"] for m in messages] == ["system", "user"]


def test_build_messages_states_whether_this_is_the_first_turn():
    first = build_messages("start", None)[0]["content"]
    assert "FIRST assistant turn" in first

    cont = build_messages("more", None, is_continuation=True)[0]["content"]
    assert "continuation of an ongoing session" in cont
    assert "NOT the first assistant turn" in cont
