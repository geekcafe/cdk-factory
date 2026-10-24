"""Prompt framework & test injection (design §2.8).

A thin **port** wraps ``questionary``/``rich`` behind an interface so the whole
wizard is driveable without a TTY in tests (NFR-1, FR-3).

``questionary`` and ``rich`` are imported **lazily inside**
``QuestionaryPrompter.__init__`` — never at module import — reinforcing NFR-2
(these operator-only deps stay off the synth/Lambda path).
"""

from __future__ import annotations

import sys
from typing import List, Optional, Protocol, Sequence, runtime_checkable


class NonInteractiveError(Exception):
    """Raised when an interactive prompt is attempted without a TTY."""


@runtime_checkable
class PromptPort(Protocol):
    """The interface the wizard drives; both prompters implement it."""

    # interactive inputs
    def select(self, message: str, choices: Sequence[str], default: Optional[str] = None) -> str: ...

    def checkbox(
        self, message: str, choices: Sequence[str], default: Optional[Sequence[str]] = None
    ) -> List[str]: ...

    def text(self, message: str, default: str = "") -> str: ...

    def password(self, message: str) -> str: ...

    def confirm(self, message: str, default: bool = False) -> bool: ...

    # rich output
    def panel(self, body: str, title: Optional[str] = None, style: str = "info") -> None: ...

    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None: ...

    def note(self, message: str, style: str = "info") -> None: ...


class QuestionaryPrompter:
    """Production prompter: ``questionary`` for input + ``rich`` for output.

    Imports ``questionary``/``rich`` lazily in ``__init__`` (never at module
    import). Every interactive method is TTY-guarded: when
    ``not sys.stdin.isatty()`` it raises :class:`NonInteractiveError` so the
    wizard can print a clear "needs a TTY or --answers" message instead of
    hanging on a prompt.
    """

    def __init__(self, console=None) -> None:
        import questionary  # lazy
        from rich.console import Console  # lazy
        from rich.panel import Panel  # lazy
        from rich.table import Table  # lazy

        self._questionary = questionary
        self._Panel = Panel
        self._Table = Table
        self._console = console if console is not None else Console()

    # -- guard --------------------------------------------------------------

    @staticmethod
    def _require_tty() -> None:
        if not sys.stdin.isatty():
            raise NonInteractiveError(
                "This step needs an interactive terminal (TTY) or a supplied "
                "--answers file."
            )

    # -- interactive inputs -------------------------------------------------

    def select(self, message: str, choices: Sequence[str], default: Optional[str] = None) -> str:
        self._require_tty()
        return self._questionary.select(
            message, choices=list(choices), default=default
        ).ask()

    def checkbox(
        self, message: str, choices: Sequence[str], default: Optional[Sequence[str]] = None
    ) -> List[str]:
        self._require_tty()
        result = self._questionary.checkbox(message, choices=list(choices)).ask()
        return list(result) if result else []

    def text(self, message: str, default: str = "") -> str:
        self._require_tty()
        return self._questionary.text(message, default=default).ask()

    def password(self, message: str) -> str:
        self._require_tty()
        return self._questionary.password(message).ask()

    def confirm(self, message: str, default: bool = False) -> bool:
        self._require_tty()
        return bool(self._questionary.confirm(message, default=default).ask())

    # -- rich output --------------------------------------------------------

    _STYLE_MAP = {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red",
    }

    def panel(self, body: str, title: Optional[str] = None, style: str = "info") -> None:
        border = self._STYLE_MAP.get(style, style)
        self._console.print(self._Panel(body, title=title, border_style=border))

    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        table = self._Table(title=title)
        for col in columns:
            table.add_column(str(col))
        for row in rows:
            table.add_row(*[str(c) for c in row])
        self._console.print(table)

    def note(self, message: str, style: str = "info") -> None:
        color = self._STYLE_MAP.get(style, style)
        self._console.print(f"[{color}]{message}[/{color}]")


class ScriptedPrompter:
    """Test double: queued answers, call recording, raises when exhausted.

    Interactive methods pop the next queued answer (FIFO) and record the call;
    ``rich``-output methods are no-op recorders. Running out of queued answers
    raises :class:`IndexError` so an under-specified test fails loudly rather
    than hanging.
    """

    def __init__(self, answers: Optional[List[object]] = None) -> None:
        self.answers: List[object] = list(answers or [])
        self.calls: List[tuple] = []
        # Output recorders (populated by panel/table/note).
        self.panels: List[tuple] = []
        self.tables: List[tuple] = []
        self.notes: List[tuple] = []

    def _next(self, kind: str, message: str):
        self.calls.append((kind, message))
        if not self.answers:
            raise IndexError(
                f"ScriptedPrompter exhausted: no queued answer for {kind}({message!r})"
            )
        return self.answers.pop(0)

    # -- interactive inputs -------------------------------------------------

    def select(self, message: str, choices: Sequence[str], default: Optional[str] = None) -> str:
        return self._next("select", message)

    def checkbox(
        self, message: str, choices: Sequence[str], default: Optional[Sequence[str]] = None
    ) -> List[str]:
        value = self._next("checkbox", message)
        return list(value) if value is not None else []

    def text(self, message: str, default: str = "") -> str:
        return self._next("text", message)

    def password(self, message: str) -> str:
        return self._next("password", message)

    def confirm(self, message: str, default: bool = False) -> bool:
        return bool(self._next("confirm", message))

    # -- rich output (no-op recorders) --------------------------------------

    def panel(self, body: str, title: Optional[str] = None, style: str = "info") -> None:
        self.panels.append((title, body, style))
        self.calls.append(("panel", title or ""))

    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        self.tables.append((title, list(columns), [list(r) for r in rows]))
        self.calls.append(("table", title))

    def note(self, message: str, style: str = "info") -> None:
        self.notes.append((message, style))
        self.calls.append(("note", message))
