"""Gitignored JSON answers persistence (design §2.6).

``AnswersStore`` is a **shape-agnostic, dict-based** store: it persists any
JSON-able ``dict`` to ``<script_dir>/.monitor/<environment>.answers.json`` and
never references any typed answers model. The typed ``MonitorAnswers`` dataclass
and its ``to_dict``/``from_dict`` live in the monitor repo, not here.

``save`` runs a secret guard first: it recursively scans **every** string value
(regardless of key) and raises :class:`SecretInAnswersError` if any value looks
like a Slack token (``^xox[baprse]-``). A Secrets Manager *name* value such as
``codepipeline-notifier/slack/bot-token`` never starts with ``xox`` and so does
NOT trip the guard.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

#: Current schema version written by this store.
SCHEMA_VERSION = 1

#: Slack token family prefix: bot ``xoxb-``, user ``xoxp-``, app ``xapp-`` family,
#: refresh ``xoxe-``, legacy ``xoxa-``/``xoxr-``/``xoxs-``. Matched on VALUE.
_SLACK_TOKEN_RE = re.compile(r"^xox[baprse]-")


class SecretInAnswersError(Exception):
    """Raised when a secret-looking value is about to be persisted to disk."""


class AnswersStore:
    """Load/save/merge non-secret wizard answers as a plain JSON dict."""

    def __init__(self, script_dir, environment: str) -> None:
        self.script_dir = Path(script_dir)
        self.environment = environment

    @property
    def path(self) -> Path:
        """``script_dir/.monitor/<environment>.answers.json``."""
        return self.script_dir / ".monitor" / f"{self.environment}.answers.json"

    def load(self) -> Optional[dict]:
        """Return the saved answers dict, or ``None`` when the file is absent.

        Tolerates/migrates an older (or missing) ``schema_version``: the loaded
        dict is returned with ``schema_version`` normalized to the current value.
        """
        if not self.path.exists():
            return None
        with open(self.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return data
        return self._migrate(data)

    def save(self, data: dict) -> Path:
        """Write *data* as pretty JSON, after running the secret guard.

        Creates ``.monitor/`` if needed. Stamps the current ``schema_version``.
        """
        self._assert_no_secrets(data)
        payload = dict(data)
        payload.setdefault("schema_version", SCHEMA_VERSION)
        payload["schema_version"] = SCHEMA_VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=4))
            fh.write("\n")
        return self.path

    def merge_defaults(self, prior: Optional[dict], cli_overrides: dict) -> dict:
        """Return ``prior`` overlaid with ``cli_overrides`` (shallow, overrides win)."""
        merged: dict = dict(prior or {})
        for key, value in (cli_overrides or {}).items():
            if value is not None:
                merged[key] = value
        return merged

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _migrate(data: dict) -> dict:
        """Normalize ``schema_version`` for a loaded dict (forward-compatible)."""
        out = dict(data)
        out["schema_version"] = SCHEMA_VERSION
        return out

    @classmethod
    def _assert_no_secrets(cls, value: object) -> None:
        """Recursively raise if any string value matches the Slack-token shape."""
        if isinstance(value, str):
            if _SLACK_TOKEN_RE.match(value):
                raise SecretInAnswersError(
                    "Refusing to persist a value that looks like a Slack token "
                    "(matches ^xox[baprse]-). Secrets must go to Secrets Manager, "
                    "never the answers file."
                )
            return
        if isinstance(value, dict):
            for item in value.values():
                cls._assert_no_secrets(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                cls._assert_no_secrets(item)
