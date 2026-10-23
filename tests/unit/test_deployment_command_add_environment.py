"""
Unit tests for the additive "[+] Add a new environment (deployment)" flow on
``CdkDeploymentCommand``.

All tests stub ``input``/``sys.stdin.isatty`` (via scripted callables and
``monkeypatch``) — no real TTY is required and no AWS calls are made. They cover:

- ``prompt_and_write_env_file`` writing the expected ``.env.<name>`` from a
  parameters list (defaults shown + Enter-accepted, required-blank enforcement,
  os.environ pre-fill precedence, overwrite confirm, skip of params without an
  env_var_name),
- ``discover_env_file_environments`` listing ``.env.*`` sorted and excluding the
  example file in env-file mode,
- ``select_environment`` offering the add entry only on a TTY and returning to a
  refreshed env list after a write,
- non-interactive invocation leaving existing behavior unchanged,
- no regression to env-file / JSON mode, and the add-flow performing no AWS
  calls, and import/construction triggering no AWS calls.
"""

import json
import os

import pytest

import cdk_factory.commands.deployment_command as dc_module
from cdk_factory.commands.deployment_command import (
    ADD_ENV_LABEL,
    CdkDeploymentCommand,
    EnvironmentConfig,
)


class ScriptedInput:
    """A scripted ``input_func`` that records prompts and returns queued answers."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.prompts = []

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        if not self._answers:
            raise AssertionError(
                f"ScriptedInput exhausted; unexpected prompt: {prompt!r}"
            )
        return self._answers.pop(0)


def _command(tmp_path):
    """Construct a command anchored at *tmp_path* (env-file mode, no deployments/)."""
    return CdkDeploymentCommand(script_dir=tmp_path)


# ---------------------------------------------------------------------------
# prompt_and_write_env_file
# ---------------------------------------------------------------------------


def test_prompt_and_write_env_file_writes_expected_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_ACCOUNT", raising=False)
    cmd = _command(tmp_path)
    parameters = [
        {"env_var_name": "ENVIRONMENT", "default_value": "prod"},
        {"env_var_name": "WORKLOAD_NAME", "value": "geekcafe-devops-monitoring"},
        {"env_var_name": "AWS_ACCOUNT"},  # required (blank default)
    ]
    # Enter for both defaulted params, then a value for the required one.
    scripted = ScriptedInput(["", "", "123456789012"])

    result = cmd.prompt_and_write_env_file(
        "prod", parameters, input_func=scripted
    )

    assert result is not None
    assert result == tmp_path / ".env.prod"
    contents = result.read_text(encoding="utf-8")
    assert contents == (
        "ENVIRONMENT=prod\n"
        "WORKLOAD_NAME=geekcafe-devops-monitoring\n"
        "AWS_ACCOUNT=123456789012\n"
    )

    # Round-trips through load_env_file.
    loaded = cmd.load_env_file(".env.prod")
    assert loaded == {
        "ENVIRONMENT": "prod",
        "WORKLOAD_NAME": "geekcafe-devops-monitoring",
        "AWS_ACCOUNT": "123456789012",
    }


def test_defaults_shown_and_enter_accepted(tmp_path, monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    cmd = _command(tmp_path)
    parameters = [
        {"env_var_name": "ENVIRONMENT", "default_value": "prod"},
        {"env_var_name": "AWS_REGION", "value": "us-east-1"},
    ]
    scripted = ScriptedInput(["", ""])

    result = cmd.prompt_and_write_env_file("stage", parameters, input_func=scripted)

    assert result is not None
    loaded = cmd.load_env_file(".env.stage")
    assert loaded == {"ENVIRONMENT": "prod", "AWS_REGION": "us-east-1"}
    # Prompt strings show the default in [...].
    assert any("[prod]" in p for p in scripted.prompts)
    assert any("[us-east-1]" in p for p in scripted.prompts)


def test_required_blank_reprompts_until_nonempty(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_ACCOUNT", raising=False)
    cmd = _command(tmp_path)
    parameters = [{"env_var_name": "AWS_ACCOUNT"}]
    # Two blanks, then a real value.
    scripted = ScriptedInput(["", "", "123456789012"])

    result = cmd.prompt_and_write_env_file("prod", parameters, input_func=scripted)

    assert result is not None
    assert cmd.load_env_file(".env.prod") == {"AWS_ACCOUNT": "123456789012"}
    # Re-prompted at least three times; prompt text marks it required.
    required_prompts = [p for p in scripted.prompts if "(required)" in p]
    assert len(required_prompts) == 3


def test_os_environ_prefill_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    cmd = _command(tmp_path)
    parameters = [
        {"env_var_name": "AWS_REGION", "value": "us-east-1"},  # env overrides value
        {"env_var_name": "ENVIRONMENT", "default_value": "prod"},  # falls back to config
    ]
    scripted = ScriptedInput(["", ""])

    result = cmd.prompt_and_write_env_file("prod", parameters, input_func=scripted)

    assert result is not None
    loaded = cmd.load_env_file(".env.prod")
    assert loaded["AWS_REGION"] == "eu-west-1"  # from os.environ, not config value
    assert loaded["ENVIRONMENT"] == "prod"  # from config default (not in env)
    assert any("[eu-west-1]" in p for p in scripted.prompts)


def test_overwrite_confirm_no_keeps_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_ACCOUNT", raising=False)
    cmd = _command(tmp_path)
    existing = tmp_path / ".env.prod"
    existing.write_text("ORIGINAL=1\n", encoding="utf-8")

    parameters = [{"env_var_name": "AWS_ACCOUNT"}]
    # One value for the param, then "n" for the overwrite confirmation (last call).
    scripted = ScriptedInput(["123456789012", "n"])

    result = cmd.prompt_and_write_env_file(
        "prod", parameters, input_func=scripted, overwrite=None
    )

    assert result is None
    assert existing.read_text(encoding="utf-8") == "ORIGINAL=1\n"


def test_overwrite_confirm_yes_rewrites_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_ACCOUNT", raising=False)
    cmd = _command(tmp_path)
    existing = tmp_path / ".env.prod"
    existing.write_text("ORIGINAL=1\n", encoding="utf-8")

    parameters = [{"env_var_name": "AWS_ACCOUNT"}]
    scripted = ScriptedInput(["123456789012", "y"])

    result = cmd.prompt_and_write_env_file(
        "prod", parameters, input_func=scripted, overwrite=None
    )

    assert result is not None
    assert existing.read_text(encoding="utf-8") == "AWS_ACCOUNT=123456789012\n"


def test_overwrite_flag_true_skips_prompt(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_ACCOUNT", raising=False)
    cmd = _command(tmp_path)
    existing = tmp_path / ".env.prod"
    existing.write_text("ORIGINAL=1\n", encoding="utf-8")

    parameters = [{"env_var_name": "AWS_ACCOUNT"}]
    # No overwrite answer queued — overwrite=True must not prompt for it.
    scripted = ScriptedInput(["123456789012"])

    result = cmd.prompt_and_write_env_file(
        "prod", parameters, input_func=scripted, overwrite=True
    )

    assert result is not None
    assert existing.read_text(encoding="utf-8") == "AWS_ACCOUNT=123456789012\n"


def test_parameter_without_env_var_name_is_skipped(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKLOAD_NAME", raising=False)
    cmd = _command(tmp_path)
    parameters = [
        {"value": "./commands/cdk_synth.sh", "cdk_parameter_name": "CdkSynthCommandFile"},
        {"env_var_name": "WORKLOAD_NAME", "value": "geekcafe-devops-monitoring"},
    ]
    scripted = ScriptedInput([""])  # only one prompt expected (WORKLOAD_NAME)

    result = cmd.prompt_and_write_env_file("prod", parameters, input_func=scripted)

    assert result is not None
    assert cmd.load_env_file(".env.prod") == {
        "WORKLOAD_NAME": "geekcafe-devops-monitoring"
    }
    # Exactly one prompt was issued (the skipped param never prompted).
    assert len(scripted.prompts) == 1
    assert "CdkSynthCommandFile" not in "".join(scripted.prompts)


# ---------------------------------------------------------------------------
# discover_env_file_environments
# ---------------------------------------------------------------------------


def test_discover_env_file_environments_lists_and_excludes_example(tmp_path):
    (tmp_path / ".env.prod").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env.sandbox").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("A=1\n", encoding="utf-8")
    cmd = _command(tmp_path)

    envs = cmd.discover_env_file_environments(git_branch="main")

    assert list(envs.keys()) == ["prod", "sandbox"]  # sorted, example excluded
    prod = envs["prod"]
    assert isinstance(prod, EnvironmentConfig)
    assert prod.env_file == ".env.prod"
    assert prod.git_branch == "main"
    # Env-file mode: no parameters -> _is_json_mode False.
    assert cmd._is_json_mode(prod) is False


def test_discover_env_file_environments_empty_returns_empty(tmp_path):
    cmd = _command(tmp_path)
    assert cmd.discover_env_file_environments() == {}


# ---------------------------------------------------------------------------
# select_environment menu wiring
# ---------------------------------------------------------------------------


class _EnvFileCommand(CdkDeploymentCommand):
    """Env-file-mode subclass driven by .env.* discovery (mirrors the target)."""

    @property
    def environments(self):
        return self.discover_env_file_environments(git_branch="main")


def _write_config_json(tmp_path, parameters):
    (tmp_path / "config.json").write_text(
        json.dumps({"cdk": {"parameters": parameters}}), encoding="utf-8"
    )


def test_menu_offers_add_entry_on_tty_and_refreshes(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_ACCOUNT", "123456789012")
    _write_config_json(
        tmp_path,
        [{"env_var_name": "AWS_ACCOUNT"}],
    )
    cmd = _EnvFileCommand(script_dir=tmp_path)

    # Interactive TTY so the add entry is offered.
    monkeypatch.setattr(dc_module.sys.stdin, "isatty", lambda: True)

    # First _interactive_select call: options should include ADD_ENV_LABEL as
    # the last entry (and no real envs yet). Select it.
    # Second call (after recursion): "prod" now exists -> select index 0.
    select_calls = {"n": 0}
    captured_options = []

    def fake_select(title, options):
        captured_options.append(list(options))
        select_calls["n"] += 1
        if select_calls["n"] == 1:
            assert options[-1] == ADD_ENV_LABEL
            assert "prod" not in options
            return len(options) - 1  # choose add entry
        # Second pass: prod present now.
        assert "prod" in options
        return options.index("prod")

    monkeypatch.setattr(cmd, "_interactive_select", fake_select)

    # _add_environment_interactive uses builtin input() for the name; the
    # parameter value comes from the AWS_ACCOUNT os.environ pre-fill (Enter).
    answers = iter(["prod", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    result = cmd.select_environment()

    assert isinstance(result, EnvironmentConfig)
    assert result.name == "prod"
    # .env.prod was written before the second (refreshed) selection pass.
    assert (tmp_path / ".env.prod").exists()
    # The add entry appeared only after discovery refreshed on the 2nd pass.
    assert ADD_ENV_LABEL in captured_options[0]
    assert "prod" in captured_options[1]


def test_menu_not_offered_when_non_interactive(tmp_path, monkeypatch):
    (tmp_path / ".env.prod").write_text("AWS_ACCOUNT=1\n", encoding="utf-8")
    cmd = _EnvFileCommand(script_dir=tmp_path)

    # Non-interactive: add entry must NOT be offered.
    monkeypatch.setattr(dc_module.sys.stdin, "isatty", lambda: False)

    captured = {}

    def fake_select(title, options):
        captured["options"] = list(options)
        return 0  # select the only real env

    monkeypatch.setattr(cmd, "_interactive_select", fake_select)

    result = cmd.select_environment()

    assert ADD_ENV_LABEL not in captured["options"]
    assert captured["options"] == ["prod"]
    assert result.name == "prod"


# ---------------------------------------------------------------------------
# No regression / no AWS
# ---------------------------------------------------------------------------


def test_add_flow_makes_no_aws_calls(tmp_path, monkeypatch):
    """The add-environment path must never touch boto3."""
    monkeypatch.delenv("AWS_ACCOUNT", raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("boto3 must not be called in the add-environment flow")

    monkeypatch.setattr(dc_module.boto3, "client", _boom)
    monkeypatch.setattr(dc_module.boto3, "Session", _boom)

    cmd = _command(tmp_path)
    parameters = [{"env_var_name": "AWS_ACCOUNT"}]
    scripted = ScriptedInput(["123456789012"])
    result = cmd.prompt_and_write_env_file("prod", parameters, input_func=scripted)
    assert result is not None


def test_import_and_construct_make_no_aws_calls(tmp_path, monkeypatch):
    """Importing/constructing the command triggers no AWS calls."""

    def _boom(*args, **kwargs):
        raise AssertionError("boto3 must not be called at import/construct time")

    monkeypatch.setattr(dc_module.boto3, "client", _boom)
    monkeypatch.setattr(dc_module.boto3, "Session", _boom)

    import importlib

    importlib.reload(dc_module)
    # Constructing with a tmp_path script_dir must not call AWS.
    dc_module.CdkDeploymentCommand(script_dir=tmp_path)
