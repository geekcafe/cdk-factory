"""Unit tests for the wizard prompt port (design §2.8)."""

import pytest

from cdk_factory.wizard.prompts import (
    NonInteractiveError,
    QuestionaryPrompter,
    ScriptedPrompter,
)


# ---------------------------------------------------------------------------
# ScriptedPrompter drives every interactive method
# ---------------------------------------------------------------------------


def test_scripted_prompter_drives_all_inputs():
    prompt = ScriptedPrompter(
        ["pipeline", ["a", "b"], "us-east-1", "xoxb-secret", True]
    )
    assert prompt.select("mode?", ["pipeline", "stack"]) == "pipeline"
    assert prompt.checkbox("pipes?", ["a", "b", "c"]) == ["a", "b"]
    assert prompt.text("region?") == "us-east-1"
    assert prompt.password("token?") == "xoxb-secret"
    assert prompt.confirm("ok?") is True
    kinds = [k for (k, _m) in prompt.calls]
    assert kinds == ["select", "checkbox", "text", "password", "confirm"]


def test_scripted_prompter_raises_when_exhausted():
    prompt = ScriptedPrompter([])
    with pytest.raises(IndexError):
        prompt.text("anything?")


def test_scripted_prompter_output_methods_record():
    prompt = ScriptedPrompter([])
    prompt.panel("body", title="T", style="warning")
    prompt.table("Review", ["c1"], [["r1"]])
    prompt.note("hello", style="info")
    assert prompt.panels == [("T", "body", "warning")]
    assert prompt.tables == [("Review", ["c1"], [["r1"]])]
    assert prompt.notes == [("hello", "info")]


# ---------------------------------------------------------------------------
# QuestionaryPrompter TTY guard
# ---------------------------------------------------------------------------


def test_questionary_prompter_raises_when_not_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    prompter = QuestionaryPrompter()
    with pytest.raises(NonInteractiveError):
        prompter.select("mode?", ["pipeline", "stack"])
    with pytest.raises(NonInteractiveError):
        prompter.text("region?")
    with pytest.raises(NonInteractiveError):
        prompter.confirm("ok?")
    with pytest.raises(NonInteractiveError):
        prompter.password("token?")
    with pytest.raises(NonInteractiveError):
        prompter.checkbox("pipes?", ["a"])
