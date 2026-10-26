"""Unit tests for ``CdkDeploymentCommand.ensure_aws_credentials``.

Credential preflight before live AWS operations (deploy/diff/destroy). A
detected ``AWS_PROFILE`` with an expired SSO session makes CDK fail opaquely
("no credentials have been configured"); this preflight checks the profile with
``aws sts get-caller-identity`` and, interactively, offers to run
``aws sso login --profile <profile>`` before handing off to CDK.

No real AWS calls and no real TTY: ``subprocess.run`` is stubbed, and
``sys.stdin.isatty`` / ``input`` are monkeypatched.
"""

import os
import subprocess
import sys

import pytest

from cdk_factory.commands.deployment_command import CdkDeploymentCommand


def _command(tmp_path):
    return CdkDeploymentCommand(script_dir=tmp_path)


class _FakeCompleted:
    def __init__(self, returncode):
        self.returncode = returncode


@pytest.fixture
def printed(monkeypatch):
    """Capture ``_print`` output as (message, color) tuples."""
    messages = []

    def _fake_print(self, message, color="white"):
        messages.append((message, color))

    monkeypatch.setattr(CdkDeploymentCommand, "_print", _fake_print)
    return messages


# -- no profile -> no-op -----------------------------------------------------


def test_no_profile_is_noop(tmp_path, monkeypatch, printed):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    calls = []
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: calls.append(a) or _FakeCompleted(0)
    )
    cmd = _command(tmp_path)

    cmd.ensure_aws_credentials()

    # Never probed sts, never prompted.
    assert calls == []
    assert printed == []


# -- valid credentials -> silent no-op ---------------------------------------


def test_valid_credentials_silent(tmp_path, monkeypatch, printed):
    monkeypatch.setenv("AWS_PROFILE", "geekcafe")

    def _run(cmd, **kwargs):
        assert cmd[:3] == ["aws", "sts", "get-caller-identity"]
        return _FakeCompleted(0)

    monkeypatch.setattr(subprocess, "run", _run)
    cmd = _command(tmp_path)

    cmd.ensure_aws_credentials()

    assert printed == []  # nothing printed when already valid


# -- invalid + TTY + accept -> runs sso login, re-checks OK ------------------


def test_invalid_tty_accept_runs_sso_login(tmp_path, monkeypatch, printed):
    monkeypatch.setenv("AWS_PROFILE", "geekcafe")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    seq = {"sts": 0, "login": 0}
    cmds = []

    def _run(cmd, **kwargs):
        cmds.append(cmd)
        if cmd[:3] == ["aws", "sts", "get-caller-identity"]:
            seq["sts"] += 1
            # First probe fails (expired), second (post-login) succeeds.
            return _FakeCompleted(1 if seq["sts"] == 1 else 0)
        if cmd[:3] == ["aws", "sso", "login"]:
            seq["login"] += 1
            return _FakeCompleted(0)
        return _FakeCompleted(0)

    monkeypatch.setattr(subprocess, "run", _run)
    cmd = _command(tmp_path)

    cmd.ensure_aws_credentials()

    assert seq["login"] == 1  # login was attempted once
    assert seq["sts"] == 2  # probed before and after login
    assert any(cmd[:3] == ["aws", "sso", "login"] for cmd in cmds)
    assert any("refreshed" in m for m, _ in printed)


# -- invalid + TTY + decline -> no login, warns ------------------------------


def test_invalid_tty_decline_no_login(tmp_path, monkeypatch, printed):
    monkeypatch.setenv("AWS_PROFILE", "geekcafe")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    cmds = []

    def _run(cmd, **kwargs):
        cmds.append(cmd)
        if cmd[:3] == ["aws", "sts", "get-caller-identity"]:
            return _FakeCompleted(1)
        return _FakeCompleted(0)

    monkeypatch.setattr(subprocess, "run", _run)
    cmd = _command(tmp_path)

    cmd.ensure_aws_credentials()

    # No sso login attempted.
    assert not any(c[:3] == ["aws", "sso", "login"] for c in cmds)
    assert any("aws sso login --profile geekcafe" in m for m, _ in printed)


# -- invalid + non-interactive -> hint only, no prompt -----------------------


def test_invalid_non_tty_hint_only(tmp_path, monkeypatch, printed):
    monkeypatch.setenv("AWS_PROFILE", "geekcafe")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

    def _boom(prompt=""):
        raise AssertionError("input() must not be called in non-interactive mode")

    monkeypatch.setattr("builtins.input", _boom)

    cmds = []

    def _run(cmd, **kwargs):
        cmds.append(cmd)
        if cmd[:3] == ["aws", "sts", "get-caller-identity"]:
            return _FakeCompleted(1)
        return _FakeCompleted(0)

    monkeypatch.setattr(subprocess, "run", _run)
    cmd = _command(tmp_path)

    cmd.ensure_aws_credentials()

    assert not any(c[:3] == ["aws", "sso", "login"] for c in cmds)
    assert any("aws sso login --profile geekcafe" in m for m, _ in printed)


# -- aws CLI missing -> treated as cannot-check (no crash) -------------------


def test_aws_cli_missing_is_safe(tmp_path, monkeypatch, printed):
    monkeypatch.setenv("AWS_PROFILE", "geekcafe")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

    def _run(cmd, **kwargs):
        raise FileNotFoundError("aws not found")

    monkeypatch.setattr(subprocess, "run", _run)
    cmd = _command(tmp_path)

    # Must not raise; probe fails -> invalid -> non-TTY hint path.
    cmd.ensure_aws_credentials()

    assert any("aws sso login --profile geekcafe" in m for m, _ in printed)


# -- deploy/diff/destroy call the preflight ----------------------------------


@pytest.mark.parametrize("op", ["run_cdk_deploy", "run_cdk_diff", "run_cdk_destroy"])
def test_cdk_ops_invoke_preflight(tmp_path, monkeypatch, op):
    called = {"preflight": 0}
    monkeypatch.setattr(
        CdkDeploymentCommand,
        "ensure_aws_credentials",
        lambda self: called.__setitem__("preflight", called["preflight"] + 1),
    )
    # Stub out the actual work so no synth/cdk runs.
    monkeypatch.setattr(CdkDeploymentCommand, "run_cdk_synth", lambda self, c: None)
    monkeypatch.setattr(CdkDeploymentCommand, "_run", lambda self, cmd: None)
    monkeypatch.setattr(CdkDeploymentCommand, "_print", lambda self, m, c="white": None)
    cmd = _command(tmp_path)

    getattr(cmd, op)("config.json")

    assert called["preflight"] == 1
