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


@pytest.mark.parametrize(
    "subcommand", ["init", "configure", "deploy", "synth", "status"]
)
def test_tenant_is_free_form_on_all_subcommands(subcommand):
    # --tenant/-t is free-form str (not choices=) on every monitor subcommand.
    ns = build_monitor_subparser().parse_args([subcommand, "--tenant", "aplos"])
    assert ns.tenant == "aplos"
    ns_short = build_monitor_subparser().parse_args([subcommand, "-t", "geekcafe"])
    assert ns_short.tenant == "geekcafe"


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
        # carry the tenant through (dispatch injects it via cli_overrides).
        data["tenant"] = (prior or {}).get("tenant", data.get("tenant", ""))
        return data

    def apply_to_notifier_json(self, answers):
        command_calls.append(
            (
                "apply_to_notifier_json",
                answers.get("environment"),
                answers.get("tenant"),
            )
        )

    def to_env_scalars(self, answers):
        # ENVIRONMENT stays the BARE env; TENANT_NAME carries the org.
        return {
            "ENVIRONMENT": answers.get("environment"),
            "TENANT_NAME": answers.get("tenant"),
        }


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
    ns = build_monitor_subparser().parse_args(
        ["init", "--tenant", "aplos", "-e", "prod"]
    )
    dispatch(cmd, "init", ns)
    # Review confirm True -> write_env_scalars + apply_to_notifier_json; synth/deploy declined.
    # Files are keyed by the composed <tenant>-<env> file_key.
    write_calls = [c for c in cmd.calls if c[0] == "write_env_scalars"]
    assert write_calls
    assert write_calls[0][1] == "aplos-prod"
    # apply_to_notifier_json saw the merged answers incl. the tenant.
    assert ("apply_to_notifier_json", "prod", "aplos") in command_calls
    assert (tmp_path / ".monitor" / "aplos-prod.answers.json").exists()
    # the bare-env answers file is NOT written.
    assert not (tmp_path / ".monitor" / "prod.answers.json").exists()


def test_dispatch_configure_runs_wizard(tmp_path):
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(
        ["configure", "--tenant", "aplos", "-e", "prod"]
    )
    dispatch(cmd, "configure", ns)
    write_calls = [c for c in cmd.calls if c[0] == "write_env_scalars"]
    assert write_calls
    assert write_calls[0][1] == "aplos-prod"


def test_dispatch_deploy_calls_run(tmp_path):
    cmd = _FakeCommand(tmp_path)
    # seed saved answers under the composed key so mode resolves
    (tmp_path / ".monitor").mkdir(parents=True)
    (tmp_path / ".monitor" / "aplos-prod.answers.json").write_text(
        '{"environment": "prod", "tenant": "aplos", "mode": "stack"}', encoding="utf-8"
    )
    ns = build_monitor_subparser().parse_args(
        ["deploy", "--tenant", "aplos", "-e", "prod"]
    )
    dispatch(cmd, "deploy", ns)
    run_calls = [c for c in cmd.calls if c[0] == "run"]
    assert run_calls
    assert run_calls[0][1]["environment_name"] == "aplos-prod"
    assert run_calls[0][1]["operation"] == "deploy"
    assert run_calls[0][1]["mode"] == "stack"


def test_dispatch_synth_calls_run(tmp_path):
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(
        ["synth", "--tenant", "aplos", "-e", "prod", "-m", "pipeline"]
    )
    dispatch(cmd, "synth", ns)
    run_calls = [c for c in cmd.calls if c[0] == "run"]
    assert run_calls[0][1]["environment_name"] == "aplos-prod"
    assert run_calls[0][1]["operation"] == "synth"
    assert run_calls[0][1]["mode"] == "pipeline"


def test_dispatch_status_no_aws_prints_config(tmp_path, capsys):
    cmd = _FakeCommand(tmp_path)
    (tmp_path / ".monitor").mkdir(parents=True)
    (tmp_path / ".monitor" / "aplos-prod.answers.json").write_text(
        '{"environment": "prod", "tenant": "aplos", "mode": "stack"}', encoding="utf-8"
    )
    ns = build_monitor_subparser().parse_args(
        ["status", "--tenant", "aplos", "-e", "prod"]
    )
    dispatch(cmd, "status", ns)
    out = capsys.readouterr().out
    assert '"mode": "stack"' in out
    # status must never call run (no deploy/synth, no AWS).
    assert not any(c[0] == "run" for c in cmd.calls)


def test_dispatch_init_non_interactive_without_answers_exits(tmp_path):
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(
        ["init", "--tenant", "aplos", "-e", "prod", "--non-interactive"]
    )
    with pytest.raises(SystemExit) as exc:
        dispatch(cmd, "init", ns)
    assert exc.value.code == 2
    assert any("non-interactive" in c[1] for c in cmd.calls if c[0] == "print")


# ---------------------------------------------------------------------------
# Tenant requirement: fail-fast, composed-key keying, migration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcommand", ["init", "configure", "deploy", "synth", "status"]
)
def test_dispatch_missing_tenant_non_interactive_fails_fast(
    tmp_path, subcommand, monkeypatch
):
    # No --tenant, no TTY, no migratable prior -> self-documenting exit 2 on EVERY
    # subcommand (the TTY check is the authoritative non-interactive signal).
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args([subcommand, "-e", "prod"])
    with pytest.raises(SystemExit) as exc:
        dispatch(cmd, subcommand, ns)
    assert exc.value.code == 2
    assert any("--tenant is required" in c[1] for c in cmd.calls if c[0] == "print")


def test_wizard_runner_honors_file_key(tmp_path):
    # WizardRunner.run uses the passed file_key for its AnswersStore,
    # write_env_scalars, and command.run calls — not the bare env.
    from cdk_factory.wizard.wizard_base import WizardRunner

    command_calls.clear()
    cmd = _FakeCommand(tmp_path)
    answers = {"environment": "prod", "tenant": "aplos"}
    WizardRunner().run(cmd, _FakeDefinition(), answers, file_key="aplos-prod")
    write_calls = [c for c in cmd.calls if c[0] == "write_env_scalars"]
    assert write_calls and write_calls[0][1] == "aplos-prod"
    assert (tmp_path / ".monitor" / "aplos-prod.answers.json").exists()


def test_dispatch_migrates_legacy_answers_on_tty(tmp_path, monkeypatch):
    # A pre-existing bare-env answers file + a TTY prompt returning the tenant
    # migrates to the composed key; the original file is left in place.
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    (tmp_path / ".monitor").mkdir(parents=True)
    legacy = tmp_path / ".monitor" / "prod.answers.json"
    legacy.write_text('{"environment": "prod", "mode": "stack"}', encoding="utf-8")
    cmd = _FakeCommand(tmp_path)
    # The migration prompt ("Tenant / organization name") is the FIRST text prompt;
    # queue it ahead of the review/synth/deploy confirms.
    cmd.wizard_prompt = ScriptedPrompter(["aplos", True, False, False])
    ns = build_monitor_subparser().parse_args(["init", "-e", "prod"])
    dispatch(cmd, "init", ns)

    migrated = tmp_path / ".monitor" / "aplos-prod.answers.json"
    assert migrated.exists()
    import json as _json

    assert _json.loads(migrated.read_text())["tenant"] == "aplos"
    # original left in place (non-destructive).
    assert legacy.exists()


def test_dispatch_migration_no_tty_fails_fast(tmp_path, monkeypatch):
    # Legacy file present but no TTY and no --tenant -> fail fast, never invent.
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    (tmp_path / ".monitor").mkdir(parents=True)
    (tmp_path / ".monitor" / "prod.answers.json").write_text(
        '{"environment": "prod", "mode": "stack"}', encoding="utf-8"
    )
    cmd = _FakeCommand(tmp_path)
    ns = build_monitor_subparser().parse_args(["init", "-e", "prod"])
    with pytest.raises(SystemExit) as exc:
        dispatch(cmd, "init", ns)
    assert exc.value.code == 2
    # no fabricated <tenant>-prod answers file was written.
    assert not list((tmp_path / ".monitor").glob("*-prod.answers.json"))


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
