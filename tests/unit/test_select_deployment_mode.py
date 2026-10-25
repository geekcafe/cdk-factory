"""
Unit tests for deployment-mode selection + --mode wiring (FEAT-002, DESIGN 8.3).

Covers select_deployment_mode(), the --mode bypass, the load-bearing
"DEPLOYMENT_MODE exported before set_environment_variables" ordering, the
non-TTY default, the TTY prompt path, the destroy path never resolving mode,
and the stack-mode / pipeline-mode front-end behaviors in run().

Uses a lightweight subclass that stubs the heavy, side-effecting steps of run()
(env application, validation, version locking, summary, CDK execution) to spies
so the tests exercise only the mode-resolution + branching logic. No AWS.
"""

import os

import pytest

from cdk_factory.commands.deployment_command import (
    CdkDeploymentCommand,
    EnvironmentConfig,
)


class _Spy:
    def __init__(self, record_env_key=None):
        self.called = False
        self.call_count = 0
        self.recorded_env = None
        self._record_env_key = record_env_key

    def __call__(self, *args, **kwargs):
        self.called = True
        self.call_count += 1
        if self._record_env_key is not None:
            self.recorded_env = os.environ.get(self._record_env_key)


class _TestCommand(CdkDeploymentCommand):
    """A CdkDeploymentCommand whose heavy run() steps are stubbed.

    Subclasses/tests patch the spy attributes to assert branching behavior.
    """

    def __init__(self, script_dir):
        super().__init__(script_dir=script_dir)
        # Spies installed by tests as needed.
        self.set_env_spy = _Spy(record_env_key="DEPLOYMENT_MODE")

    @property
    def environments(self):
        return {
            "test": EnvironmentConfig(
                name="test", env_file=".env.test", git_branch="main"
            )
        }

    # --- stub the heavy, side-effecting steps ---
    def load_env_file(self, env_file):
        return {}

    def set_environment_variables(self, env_config, env_vars):
        # Record DEPLOYMENT_MODE at call time (sequencing assertion).
        self.set_env_spy(env_config, env_vars)

    def validate_required_variables(self):
        return None

    def _prompt_version_locking(self, env_config):
        return None

    def display_configuration_summary(self, config_file):
        return None


def _make(tmp_path):
    return _TestCommand(script_dir=tmp_path)


@pytest.fixture(autouse=True)
def _clean_mode_env(monkeypatch):
    """Isolate DEPLOYMENT_MODE / gate vars so they do not leak between tests."""
    for key in ("DEPLOYMENT_MODE", "PIPELINE_ENABLED", "STACK_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    yield


# ---------------------------------------------------------------------------
# select_deployment_mode (pure selection)
# ---------------------------------------------------------------------------


def test_tty_prompt_path_returns_stack(tmp_path, monkeypatch):
    cmd = _make(tmp_path)
    monkeypatch.setattr(
        CdkDeploymentCommand, "_interactive_select", staticmethod(lambda title, opts: 1)
    )
    assert cmd.select_deployment_mode() == "stack"


def test_tty_prompt_path_returns_pipeline(tmp_path, monkeypatch):
    cmd = _make(tmp_path)
    monkeypatch.setattr(
        CdkDeploymentCommand, "_interactive_select", staticmethod(lambda title, opts: 0)
    )
    assert cmd.select_deployment_mode() == "pipeline"


def test_default_reorders_so_default_is_option_one(tmp_path, monkeypatch):
    """A supplied default is placed first (option 1 / menu default).

    The operator always picks index 0 (the default); asserting the returned mode
    equals the supplied default proves the reorder put it first. With no default,
    the legacy order (pipeline first) is preserved.
    """
    captured = {}

    def _spy_select(title, opts):
        captured["opts"] = list(opts)
        return 0  # operator accepts the default (first option)

    monkeypatch.setattr(
        CdkDeploymentCommand, "_interactive_select", staticmethod(_spy_select)
    )
    cmd = _make(tmp_path)

    # default="stack" -> stack is option 1 and is what index 0 returns.
    assert cmd.select_deployment_mode(default="stack") == "stack"
    assert captured["opts"] == ["stack", "pipeline"]

    # No default -> legacy order preserved (pipeline first).
    assert cmd.select_deployment_mode() == "pipeline"
    assert captured["opts"] == ["pipeline", "stack"]

    # Unknown/None default -> legacy order (defensive).
    assert cmd.select_deployment_mode(default="bogus") == "pipeline"
    assert captured["opts"] == ["pipeline", "stack"]


def test_configured_default_mode_reads_config_json(tmp_path):
    """_configured_default_mode reads DEPLOYMENT_MODE's default from config.json."""
    import json as _json

    (tmp_path / "config.json").write_text(
        _json.dumps(
            {
                "cdk": {
                    "parameters": [
                        {
                            "env_var_name": "DEPLOYMENT_MODE",
                            "default_value": "stack",
                        }
                    ]
                }
            }
        )
    )
    cmd = _make(tmp_path)
    assert cmd._configured_default_mode() == "stack"


# ---------------------------------------------------------------------------
# --mode bypass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("explicit_mode", ["stack", "pipeline"])
def test_mode_arg_bypasses_prompt(tmp_path, monkeypatch, explicit_mode):
    cmd = _make(tmp_path)
    synth_spy = _Spy()
    cmd.run_cdk_synth = synth_spy  # type: ignore[assignment]

    def _raise(*a, **k):
        raise AssertionError("select_deployment_mode must not be called with --mode")

    monkeypatch.setattr(cmd, "select_deployment_mode", _raise)
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)

    cmd.run(environment_name="test", operation="synth", mode=explicit_mode)

    assert os.environ["DEPLOYMENT_MODE"] == explicit_mode
    assert synth_spy.called


# ---------------------------------------------------------------------------
# Sequencing: DEPLOYMENT_MODE set BEFORE set_environment_variables
# ---------------------------------------------------------------------------


def test_deployment_mode_set_before_set_environment_variables(tmp_path):
    cmd = _make(tmp_path)
    cmd.run_cdk_synth = _Spy()  # type: ignore[assignment]

    cmd.run(environment_name="test", operation="synth", mode="stack")

    # The spy recorded DEPLOYMENT_MODE at the moment set_environment_variables ran.
    assert cmd.set_env_spy.recorded_env == "stack"


def test_monitoring_style_override_derives_gate_vars(tmp_path):
    """A monitoring-style subclass maps DEPLOYMENT_MODE -> PIPELINE/STACK_ENABLED."""

    class _MonitoringCommand(_TestCommand):
        def set_environment_variables(self, env_config, env_vars):
            mode = os.environ.get("DEPLOYMENT_MODE", "pipeline")
            os.environ["PIPELINE_ENABLED"] = "true" if mode == "pipeline" else "false"
            os.environ["STACK_ENABLED"] = "true" if mode == "stack" else "false"

    cmd = _MonitoringCommand(script_dir=tmp_path)
    cmd.run_cdk_synth = _Spy()  # type: ignore[assignment]

    cmd.run(environment_name="test", operation="synth", mode="stack")
    assert os.environ["STACK_ENABLED"] == "true"
    assert os.environ["PIPELINE_ENABLED"] == "false"

    cmd2 = _MonitoringCommand(script_dir=tmp_path)
    cmd2.run_cdk_synth = _Spy()  # type: ignore[assignment]
    cmd2.run(environment_name="test", operation="synth", mode="pipeline")
    assert os.environ["STACK_ENABLED"] == "false"
    assert os.environ["PIPELINE_ENABLED"] == "true"


# ---------------------------------------------------------------------------
# Non-TTY default
# ---------------------------------------------------------------------------


def test_non_tty_defaults_to_pipeline(tmp_path, monkeypatch):
    cmd = _make(tmp_path)
    cmd.run_cdk_synth = _Spy()  # type: ignore[assignment]
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    def _raise(*a, **k):
        raise AssertionError("must not prompt in non-TTY")

    monkeypatch.setattr(cmd, "select_deployment_mode", _raise)
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)

    cmd.run(environment_name="test", operation="synth", mode=None)

    assert os.environ["DEPLOYMENT_MODE"] == "pipeline"


def test_run_does_not_prompt_mode_on_tty_when_mode_is_none(tmp_path, monkeypatch):
    """run() no longer prompts mode: the redundant second select_deployment_mode()
    call was removed. Mode is decided at configure time (in the add-environment
    sub-flow) and baked into .env.<name>; run() adopts it after env application.

    This is safe ONLY because environment_name="test" is pre-selected, so
    select_environment()/_add_environment_interactive() (which legitimately call
    select_deployment_mode for a NEW env) is never entered — we assert only that
    top-of-run() no longer prompts.
    """
    cmd = _make(tmp_path)
    cmd.run_cdk_synth = _Spy()  # type: ignore[assignment]
    # Fallback resolves to "pipeline", so run() reaches the pipeline-only
    # _prompt_devops_config wizard — stub it so no interactive prompt fires.
    cmd._prompt_devops_config = _Spy()  # type: ignore[assignment]
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def _raise(*a, **k):
        raise AssertionError("run() must not prompt mode when mode is None")

    monkeypatch.setattr(cmd, "select_deployment_mode", _raise)
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)

    # Must not raise; synth must run; stubbed set_environment_variables sets no
    # DEPLOYMENT_MODE, so the fallback/recompute resolves to "pipeline".
    cmd.run(environment_name="test", operation="synth", mode=None)

    assert cmd.run_cdk_synth.called
    assert os.environ["DEPLOYMENT_MODE"] == "pipeline"


# ---------------------------------------------------------------------------
# Destroy path never resolves mode
# ---------------------------------------------------------------------------


def test_destroy_never_resolves_mode(tmp_path, monkeypatch):
    cmd = _make(tmp_path)
    destroy_spy = _Spy()
    cmd.run_cdk_destroy = destroy_spy  # type: ignore[assignment]

    def _raise(*a, **k):
        raise AssertionError("select_deployment_mode must not run for destroy")

    monkeypatch.setattr(cmd, "select_deployment_mode", _raise)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")

    cmd.run(environment_name="test", operation="destroy")

    assert destroy_spy.called


# ---------------------------------------------------------------------------
# Stack-mode front-end
# ---------------------------------------------------------------------------


def test_stack_mode_non_interactive_skips_wizard_and_runner(
    tmp_path, monkeypatch, capsys
):
    cmd = _make(tmp_path)
    deploy_spy = _Spy()
    runner_spy = _Spy()
    wizard_spy = _Spy()
    cmd.run_cdk_deploy = deploy_spy  # type: ignore[assignment]
    cmd.run_post_deploy_steps = runner_spy  # type: ignore[assignment]
    cmd._prompt_devops_config = wizard_spy  # type: ignore[assignment]
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    cmd.run(environment_name="test", operation="deploy", mode="stack")

    assert deploy_spy.called
    assert not wizard_spy.called  # wizard skipped in stack mode
    assert not runner_spy.called  # non-interactive: not auto-run
    out = capsys.readouterr().out
    assert "does NOT auto-run post_steps" in out


def test_stack_mode_tty_yes_runs_runner(tmp_path, monkeypatch):
    cmd = _make(tmp_path)
    cmd.run_cdk_deploy = _Spy()  # type: ignore[assignment]
    runner_spy = _Spy()
    cmd.run_post_deploy_steps = runner_spy  # type: ignore[assignment]
    cmd._prompt_devops_config = _Spy()  # type: ignore[assignment]
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")

    cmd.run(environment_name="test", operation="deploy", mode="stack")

    assert runner_spy.called


def test_stack_mode_tty_no_declines_runner(tmp_path, monkeypatch):
    cmd = _make(tmp_path)
    cmd.run_cdk_deploy = _Spy()  # type: ignore[assignment]
    runner_spy = _Spy()
    cmd.run_post_deploy_steps = runner_spy  # type: ignore[assignment]
    cmd._prompt_devops_config = _Spy()  # type: ignore[assignment]
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "n")

    cmd.run(environment_name="test", operation="deploy", mode="stack")

    assert not runner_spy.called


# ---------------------------------------------------------------------------
# Pipeline-mode front-end unchanged
# ---------------------------------------------------------------------------


def test_pipeline_mode_runs_wizard_and_never_offers_runner(tmp_path, monkeypatch):
    cmd = _make(tmp_path)
    cmd.run_cdk_deploy = _Spy()  # type: ignore[assignment]
    runner_spy = _Spy()
    wizard_spy = _Spy()
    cmd.run_post_deploy_steps = runner_spy  # type: ignore[assignment]
    cmd._prompt_devops_config = wizard_spy  # type: ignore[assignment]
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    cmd.run(environment_name="test", operation="deploy", mode="pipeline")

    assert wizard_spy.called
    assert not runner_spy.called
