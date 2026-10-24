"""Unit tests for the wizard AnswersStore (design §2.6)."""

import json

import pytest

from cdk_factory.wizard.answers_store import (
    SCHEMA_VERSION,
    AnswersStore,
    SecretInAnswersError,
)


# ---------------------------------------------------------------------------
# load absent / save round-trip / per-env path / .monitor creation
# ---------------------------------------------------------------------------


def test_load_absent_returns_none(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    assert store.load() is None


def test_path_is_per_env(tmp_path):
    assert AnswersStore(tmp_path, "prod").path == tmp_path / ".monitor" / "prod.answers.json"
    assert AnswersStore(tmp_path, "dev").path == tmp_path / ".monitor" / "dev.answers.json"


def test_save_creates_monitor_dir_and_round_trips(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    data = {"environment": "prod", "mode": "pipeline", "pipelines": {"mode": "all"}}
    path = store.save(data)
    assert path.exists()
    assert (tmp_path / ".monitor").is_dir()
    loaded = store.load()
    assert loaded["environment"] == "prod"
    assert loaded["mode"] == "pipeline"
    assert loaded["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# schema_version migration
# ---------------------------------------------------------------------------


def test_schema_version_migrated_on_load(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    store.path.parent.mkdir(parents=True)
    store.path.write_text(json.dumps({"environment": "prod"}), encoding="utf-8")
    loaded = store.load()
    assert loaded["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# merge_defaults
# ---------------------------------------------------------------------------


def test_merge_defaults_overrides_win_and_ignore_none(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    merged = store.merge_defaults(
        {"environment": "prod", "mode": "stack"},
        {"mode": "pipeline", "region": None, "profile": "p"},
    )
    assert merged["environment"] == "prod"
    assert merged["mode"] == "pipeline"
    assert merged["profile"] == "p"
    assert "region" not in merged  # None override skipped


# ---------------------------------------------------------------------------
# Secret guard
# ---------------------------------------------------------------------------


def test_secret_guard_raises_on_xoxb_under_any_key(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    with pytest.raises(SecretInAnswersError):
        store.save({"anything": "xoxb-1234567890-abcdef"})


def test_secret_guard_raises_on_non_xoxb_family_nested(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    with pytest.raises(SecretInAnswersError):
        store.save({"nested": {"deep": ["safe", "xoxp-user-token"]}})
    with pytest.raises(SecretInAnswersError):
        store.save({"nested": {"deep": "xoxe-refresh-token"}})


def test_secret_guard_does_not_raise_on_secret_name_path(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    # A Secrets Manager NAME value must NOT trip the guard.
    data = {
        "slack_bot_token_secret_name": "codepipeline-notifier/slack/bot-token",
        "token_action": "print_command",
    }
    path = store.save(data)
    assert path.exists()
    loaded = store.load()
    assert loaded["slack_bot_token_secret_name"] == "codepipeline-notifier/slack/bot-token"


def test_secret_guard_runs_before_file_written(tmp_path):
    store = AnswersStore(tmp_path, "prod")
    with pytest.raises(SecretInAnswersError):
        store.save({"token": "xoxb-secret"})
    # Nothing was written.
    assert not store.path.exists()
