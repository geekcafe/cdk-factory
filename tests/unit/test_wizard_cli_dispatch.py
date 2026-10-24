"""Unit tests for monitor subparser + dispatch + legacy split (design §2.2)."""

import sys

import pytest

from cdk_factory.wizard.cli import build_monitor_subparser, dispatch
from cdk_factory.wizard.prompts import ScriptedPrompter
from cdk_factory.wizard.wizard_base import WizardDefinition


# ---------------------------------------------------------------------------
# Argparse surface
# ---------------------------------------------------------------------------


def test_subcommand_required():
    parser = build_monitor_subparser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_bad_subcommand_errors():
    parser = build_monitor_subparser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


def test_init_environment_is_free_form():
    # First-run env that does not exist yet must be accepted (no choices=).
    ns = build_monitor_subparser().parse_args(["init", "-e", "prod"])
    assert ns.subcommand == "init"
    assert ns.environment == "prod"


def test_deploy_parses_mode_and_dry_run():
    ns = build_monitor_subparser().parse_args(
        ["deploy", "-e", "prod", "-m", "stack", "--dry-run"]
    )
    assert ns.subcommand == "deploy"
    assert ns.mode == "stack"
    assert ns.dry_run is True


# ---------------------------------------------------------------------------
# Dispatch routing
# ---------------------------------------------------------------------------


class _FakeDefinition(WizardDefinition):
    def secret_id(self):
        return "some/secret"

    def read_workload_name(self):
        return "wl"

    def read_repo_owner(self):
        return "geekcafe"

    def collect_answers(self, command, prompt, inspector, prior):
        data = dict(prior or {})
        data["mode"] = "stack"  # skip connection flow
        return data

    def apply_to_notifier_json(self, answers):
        command_calls.append(("apply_to_notifier_json", answers.get("environment")))

    def to_env_scalars(self, answers):
        return {"ENVIRONMENT": answers.get("environment")}


command_calls = []


class _FakeCommand:
    def __init__(self, tmp_path):
        self.script_dir = tmp_path
        self.calls = []
        self.wizard_prompt = ScriptedPrompter([True, False, False])
        self.wizard_inspector = object()

    def wizard_definition(self):
        return _FakeDefinition()

    def _print(self, message, color="white"):
        self.calls.append(("print", message, color))

    def select_deployment_mode(self):
        self.calls.append(("select_deployment_mode",))
        return "stack"

    def write_env_scalars(self, env, scalars):
        self.calls.append(("write_env_scalars", env, scalars))
        return self.script_dir / f".env.{env}"

    def run(self, **kwargs):
        self.calls.append(("run", kwargs))


def test_dispatch_init_runs_wizard(tmp_path):
    command_calls.clear()
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(["init", "-e", "prod"])
    dispatch(cmd, "init", ns)
    # Review confirm True -> write_env_scalars + apply_to_notifier_json; synth/deploy declined.
    assert any(c[0] == "write_env_scalars" for c in cmd.calls)
    assert ("apply_to_notifier_json", "prod") in command_calls
    assert (tmp_path / ".monitor" / "prod.answers.json").exists()


def test_dispatch_configure_runs_wizard(tmp_path):
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(["configure", "-e", "prod"])
    dispatch(cmd, "configure", ns)
    assert any(c[0] == "write_env_scalars" for c in cmd.calls)


def test_dispatch_deploy_calls_run(tmp_path):
    cmd = _FakeCommand(tmp_path)
    # seed saved answers so mode resolves
    (tmp_path / ".monitor").mkdir(parents=True)
    (tmp_path / ".monitor" / "prod.answers.json").write_text(
        '{"environment": "prod", "mode": "stack"}', encoding="utf-8"
    )
    ns = build_monitor_subparser().parse_args(["deploy", "-e", "prod"])
    dispatch(cmd, "deploy", ns)
    run_calls = [c for c in cmd.calls if c[0] == "run"]
    assert run_calls
    assert run_calls[0][1]["operation"] == "deploy"
    assert run_calls[0][1]["mode"] == "stack"


def test_dispatch_synth_calls_run(tmp_path):
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(["synth", "-e", "prod", "-m", "pipeline"])
    dispatch(cmd, "synth", ns)
    run_calls = [c for c in cmd.calls if c[0] == "run"]
    assert run_calls[0][1]["operation"] == "synth"
    assert run_calls[0][1]["mode"] == "pipeline"


def test_dispatch_status_no_aws_prints_config(tmp_path, capsys):
    cmd = _FakeCommand(tmp_path)
    (tmp_path / ".monitor").mkdir(parents=True)
    (tmp_path / ".monitor" / "prod.answers.json").write_text(
        '{"environment": "prod", "mode": "stack"}', encoding="utf-8"
    )
    ns = build_monitor_subparser().parse_args(["status", "-e", "prod"])
    dispatch(cmd, "status", ns)
    out = capsys.readouterr().out
    assert '"mode": "stack"' in out
    # status must never call run (no deploy/synth, no AWS).
    assert not any(c[0] == "run" for c in cmd.calls)


def test_dispatch_init_non_interactive_without_answers_exits(tmp_path):
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(["init", "-e", "prod", "--non-interactive"])
    with pytest.raises(SystemExit) as exc:
        dispatch(cmd, "init", ns)
    assert exc.value.code == 2
    assert any("non-interactive" in c[1] for c in cmd.calls if c[0] == "print")


# ---------------------------------------------------------------------------
# Legacy no-subcommand path still reaches run(...) unchanged
# ---------------------------------------------------------------------------


def test_legacy_path_unchanged_when_no_monitor_token(tmp_path, monkeypatch):
    from cdk_factory.commands.deployment_command import (
        CdkDeploymentCommand,
        EnvironmentConfig,
    )

    run_calls = []

    class _LegacyCommand(CdkDeploymentCommand):
        @property
        def environments(self):
            return {
                "test": EnvironmentConfig(
                    name="test", env_file=".env.test", git_branch="main"
                )
            }

        def run(self, **kwargs):
            run_calls.append(kwargs)

    monkeypatch.setattr(sys, "argv", ["prog", "-e", "test", "-o", "synth"])
    _LegacyCommand.main(script_dir=tmp_path)
    assert run_calls
    assert run_calls[0]["environment_name"] == "test"
    assert run_calls[0]["operation"] == "synth"


def test_monitor_token_routes_to_run_wizard(tmp_path, monkeypatch):
    from cdk_factory.commands.deployment_command import (
        CdkDeploymentCommand,
        EnvironmentConfig,
    )

    wizard_calls = []

    class _MonitorCommand(CdkDeploymentCommand):
        @property
        def environments(self):
            return {}

        def run_wizard(self, subcommand, ns):
            wizard_calls.append((subcommand, ns.environment))

    monkeypatch.setattr(sys, "argv", ["prog", "monitor", "init", "-e", "prod"])
    _MonitorCommand.main(script_dir=tmp_path)
    assert wizard_calls == [("init", "prod")]
