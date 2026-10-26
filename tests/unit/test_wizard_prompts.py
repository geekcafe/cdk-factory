"""Unit tests for the wizard prompt port (design §2.8)."""

import pytest

from cdk_factory.wizard.prompts import (
    USE_DEFAULT,
    NonInteractiveError,
    PromptCancelledError,
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
    # calls entries are now uniformly 3-wide: (kind, message, details).
    kinds = [k for (k, _m, _d) in prompt.calls]
    assert kinds == ["select", "checkbox", "text", "password", "confirm"]
    # select/checkbox record their choices; text records its default.
    select_call = next(c for c in prompt.calls if c[0] == "select")
    assert select_call[2]["choices"] == ["pipeline", "stack"]
    checkbox_call = next(c for c in prompt.calls if c[0] == "checkbox")
    assert checkbox_call[2]["choices"] == ["a", "b", "c"]
    text_call = next(c for c in prompt.calls if c[0] == "text")
    assert "default" in text_call[2]


def test_scripted_prompter_use_default_returns_caller_default():
    """A queued USE_DEFAULT sentinel returns the caller's default per method."""
    prompt = ScriptedPrompter([USE_DEFAULT, USE_DEFAULT, USE_DEFAULT, USE_DEFAULT])
    assert prompt.select("mode?", ["pipeline", "stack"], default="stack") == "stack"
    assert prompt.text("name?", default="prod") == "prod"
    assert prompt.confirm("ok?", default=True) is True
    assert prompt.checkbox("pipes?", ["a", "b"], default=["a"]) == ["a"]


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


# ---------------------------------------------------------------------------
# QuestionaryPrompter: an aborted .ask() (None) raises PromptCancelledError
# ---------------------------------------------------------------------------


class _AbortingQuestionary:
    """Fake questionary whose every builder's .ask() returns None (Ctrl-C/ESC)."""

    class _Q:
        def ask(self):
            return None

    def select(self, *a, **k):
        return self._Q()

    def checkbox(self, *a, **k):
        return self._Q()

    def text(self, *a, **k):
        return self._Q()

    def password(self, *a, **k):
        return self._Q()

    def confirm(self, *a, **k):
        return self._Q()


def _tty_prompter(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    prompter = QuestionaryPrompter()
    prompter._questionary = _AbortingQuestionary()
    return prompter


def test_questionary_cancel_raises_on_select(monkeypatch):
    prompter = _tty_prompter(monkeypatch)
    with pytest.raises(PromptCancelledError):
        prompter.select("mode?", ["pipeline", "stack"])


def test_questionary_cancel_raises_on_text(monkeypatch):
    prompter = _tty_prompter(monkeypatch)
    with pytest.raises(PromptCancelledError):
        prompter.text("name?")


def test_questionary_cancel_raises_on_confirm(monkeypatch):
    """The key bug: a cancelled confirm must NOT coerce to False (which the
    channel loop would swallow and re-ask forever)."""
    prompter = _tty_prompter(monkeypatch)
    with pytest.raises(PromptCancelledError):
        prompter.confirm("add a channel?", default=True)


def test_questionary_cancel_raises_on_password(monkeypatch):
    prompter = _tty_prompter(monkeypatch)
    with pytest.raises(PromptCancelledError):
        prompter.password("token?")


def test_questionary_cancel_raises_on_checkbox(monkeypatch):
    """checkbox returns [] for 'nothing selected' but None means abort -> cancel."""
    prompter = _tty_prompter(monkeypatch)
    with pytest.raises(PromptCancelledError):
        prompter.checkbox("pipes?", ["a", "b"])
