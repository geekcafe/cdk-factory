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

    result = cmd.prompt_and_write_env_file("prod", parameters, input_func=scripted)

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


def test_shown_default_ignores_os_environ(tmp_path, monkeypatch):
    """The prompt's shown default comes ONLY from config.json, never os.environ.

    Seeding a brand-new .env from the operator's ambient shell would bake stale
    cross-session values (e.g. a leftover exported AWS_REGION/AWS_ACCOUNT) into
    the written file. So a set env var must be IGNORED: the shown default is the
    config.json ``value``/``default_value``, and a param with neither is required
    (prompted until non-empty) even when an env var is present.
    """
    monkeypatch.setenv("AWS_REGION", "eu-west-1")  # must be IGNORED
    monkeypatch.setenv(
        "AWS_ACCOUNT", "999999999999"
    )  # must be IGNORED (required field)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    cmd = _command(tmp_path)
    parameters = [
        {
            "env_var_name": "AWS_REGION",
            "value": "us-east-1",
        },  # config value wins over env
        {"env_var_name": "ENVIRONMENT", "default_value": "prod"},  # config default
        {"env_var_name": "AWS_ACCOUNT"},  # no default -> required despite the env var
    ]
    # AWS_REGION + ENVIRONMENT Enter-accept their config defaults; AWS_ACCOUNT is
    # required and must be typed (the env var does not satisfy it).
    scripted = ScriptedInput(["", "", "123456789012"])

    result = cmd.prompt_and_write_env_file("prod", parameters, input_func=scripted)

    assert result is not None
    loaded = cmd.load_env_file(".env.prod")
    assert loaded["AWS_REGION"] == "us-east-1"  # config value, NOT the eu-west-1 env
    assert loaded["ENVIRONMENT"] == "prod"  # config default
    assert loaded["AWS_ACCOUNT"] == "123456789012"  # typed, NOT the leaked env
    # The shown default for AWS_REGION was the config value, not the env var.
    assert any("[us-east-1]" in p for p in scripted.prompts)
    assert not any("eu-west-1" in p for p in scripted.prompts)
    # AWS_ACCOUNT was prompted as required (no bracketed default from the env).
    assert any("AWS_ACCOUNT (required)" in p for p in scripted.prompts)


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
        {
            "value": "./commands/cdk_synth.sh",
            "cdk_parameter_name": "CdkSynthCommandFile",
        },
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
    # AWS_ACCOUNT has no config default -> it is a REQUIRED prompt. The shown
    # default is NOT seeded from os.environ (that would bake stale shell state
    # into a brand-new .env), so a leftover exported AWS_ACCOUNT must be ignored
    # here and the value must come from the typed answer below.
    monkeypatch.setenv("AWS_ACCOUNT", "999999999999")  # must be IGNORED by the prompt
    _write_config_json(
        tmp_path,
        [{"env_var_name": "AWS_ACCOUNT"}],
    )
    cmd = _EnvFileCommand(script_dir=tmp_path)

    # Interactive TTY so the add entry is offered.
    monkeypatch.setattr(dc_module.sys.stdin, "isatty", lambda: True)

    # Environment-selection menus. The add-environment sub-flow now also asks
    # the deployment mode (via select_deployment_mode -> _interactive_select),
    # so distinguish the menus by title rather than call order:
    #   1) env menu (add entry offered, no real envs yet) -> choose add entry
    #   2) mode menu ('pipeline'/'stack') -> choose stack
    #   3) env menu refreshed ('prod' now exists) -> choose prod
    env_menu_options = []

    def fake_select(title, options):
        if title.startswith("Select deployment mode"):
            assert list(options) == ["pipeline", "stack"]
            return options.index("stack")
        env_menu_options.append(list(options))
        if len(env_menu_options) == 1:
            assert options[-1] == ADD_ENV_LABEL
            assert "prod" not in options
            return len(options) - 1  # choose add entry
        # Refreshed env menu: prod present now.
        assert "prod" in options
        return options.index("prod")

    monkeypatch.setattr(cmd, "_interactive_select", fake_select)

    # _add_environment_interactive uses builtin input() for the name; AWS_ACCOUNT
    # is a required prompt (no config default, no os.environ seeding), so a real
    # value must be typed.
    answers = iter(["prod", "123456789012"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    result = cmd.select_environment()

    assert isinstance(result, EnvironmentConfig)
    assert result.name == "prod"
    # .env.prod was written before the second (refreshed) selection pass.
    assert (tmp_path / ".env.prod").exists()
    # The typed value was written — NOT the leaked os.environ value.
    assert "AWS_ACCOUNT=123456789012" in (tmp_path / ".env.prod").read_text()
    assert "999999999999" not in (tmp_path / ".env.prod").read_text()
    # The add entry appeared only on the first env menu; prod on the refreshed one.
    assert ADD_ENV_LABEL in env_menu_options[0]
    assert "prod" in env_menu_options[1]


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


# ---------------------------------------------------------------------------
# Mode-first prompting: mode_gated / mode_derived (prompt_and_write_env_file)
# ---------------------------------------------------------------------------

from cdk_factory.commands.deployment_command import DERIVED_MODE_VALUES


def _mode_parameters():
    """A monitor-shaped parameters list: two mode_gated repo vars + three
    mode_derived gate vars, with plain vars interspersed."""
    return [
        {"env_var_name": "ENVIRONMENT", "default_value": "prod"},
        {"env_var_name": "WORKLOAD_NAME", "value": "devops-monitoring"},
        {"env_var_name": "AWS_REGION", "value": "us-east-1"},
        {
            "env_var_name": "CODE_REPOSITORY_NAME",
            "value": "geekcafe/geek-cafe-devops-monitoring",
            "mode_gated": True,
        },
        {
            "env_var_name": "CODE_REPOSITORY_ARN",
            "default_value": "arn:aws:codeconnections:...",
            "mode_gated": True,
        },
        {"env_var_name": "GIT_BRANCH", "value": "main"},
        {"env_var_name": "DEPLOYMENT_MODE", "value": "pipeline", "mode_derived": True},
        {"env_var_name": "PIPELINE_ENABLED", "value": "false", "mode_derived": True},
        {"env_var_name": "STACK_ENABLED", "value": "true", "mode_derived": True},
    ]


def _clear_mode_env(monkeypatch):
    for var in (
        "ENVIRONMENT",
        "WORKLOAD_NAME",
        "AWS_REGION",
        "CODE_REPOSITORY_NAME",
        "CODE_REPOSITORY_ARN",
        "GIT_BRANCH",
        "DEPLOYMENT_MODE",
        "PIPELINE_ENABLED",
        "STACK_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)


def test_pipeline_mode_prompts_repo_vars_and_writes_pipeline_triple(
    tmp_path, monkeypatch
):
    _clear_mode_env(monkeypatch)
    cmd = _command(tmp_path)
    parameters = _mode_parameters()
    # Prompted (in declaration order), skipping the three mode_derived gate vars:
    # ENVIRONMENT, WORKLOAD_NAME, AWS_REGION, CODE_REPOSITORY_NAME,
    # CODE_REPOSITORY_ARN, GIT_BRANCH -> six Enter-accept answers.
    scripted = ScriptedInput(["", "", "", "", "", ""])

    result = cmd.prompt_and_write_env_file(
        "prod",
        parameters,
        input_func=scripted,
        mode="pipeline",
        derived_values=DERIVED_MODE_VALUES["pipeline"],
    )

    assert result is not None
    loaded = cmd.load_env_file(".env.prod")
    # Repo vars ARE present in pipeline mode.
    assert loaded["CODE_REPOSITORY_NAME"] == "geekcafe/geek-cafe-devops-monitoring"
    assert loaded["CODE_REPOSITORY_ARN"] == "arn:aws:codeconnections:..."
    # Derived pipeline triple written verbatim.
    assert loaded["DEPLOYMENT_MODE"] == "pipeline"
    assert loaded["PIPELINE_ENABLED"] == "true"
    assert loaded["STACK_ENABLED"] == "false"
    # The three gate params were NEVER prompted.
    joined = "".join(scripted.prompts)
    assert "DEPLOYMENT_MODE" not in joined
    assert "PIPELINE_ENABLED" not in joined
    assert "STACK_ENABLED" not in joined
    # Repo vars WERE prompted in pipeline mode.
    assert "CODE_REPOSITORY_NAME" in joined
    assert "CODE_REPOSITORY_ARN" in joined
    # Derived triple is written at the END (declaration order preserved).
    contents = result.read_text(encoding="utf-8").splitlines()
    assert contents[-3:] == [
        "DEPLOYMENT_MODE=pipeline",
        "PIPELINE_ENABLED=true",
        "STACK_ENABLED=false",
    ]


def test_stack_mode_skips_repo_vars_and_writes_stack_triple(tmp_path, monkeypatch):
    _clear_mode_env(monkeypatch)
    cmd = _command(tmp_path)
    parameters = _mode_parameters()
    # Repo vars skipped and gate vars derived -> only ENVIRONMENT, WORKLOAD_NAME,
    # AWS_REGION, GIT_BRANCH prompted -> four Enter-accept answers.
    scripted = ScriptedInput(["", "", "", ""])

    result = cmd.prompt_and_write_env_file(
        "prod",
        parameters,
        input_func=scripted,
        mode="stack",
        derived_values=DERIVED_MODE_VALUES["stack"],
    )

    assert result is not None
    loaded = cmd.load_env_file(".env.prod")
    # Repo vars ABSENT from the file in stack mode.
    assert "CODE_REPOSITORY_NAME" not in loaded
    assert "CODE_REPOSITORY_ARN" not in loaded
    # Derived stack triple written verbatim.
    assert loaded["DEPLOYMENT_MODE"] == "stack"
    assert loaded["PIPELINE_ENABLED"] == "false"
    assert loaded["STACK_ENABLED"] == "true"
    # Repo vars and gate vars were NEVER prompted.
    joined = "".join(scripted.prompts)
    assert "CODE_REPOSITORY_NAME" not in joined
    assert "CODE_REPOSITORY_ARN" not in joined
    assert "DEPLOYMENT_MODE" not in joined
    assert "PIPELINE_ENABLED" not in joined
    assert "STACK_ENABLED" not in joined
    # Exactly four prompts (the non-gated, non-derived params).
    assert len(scripted.prompts) == 4


def test_no_mode_still_prompts_gated_param_regression(tmp_path, monkeypatch):
    """When mode is None (legacy caller), a mode_gated param is still prompted
    and mode_derived params fall through to normal prompting — today's behavior."""
    _clear_mode_env(monkeypatch)
    cmd = _command(tmp_path)
    parameters = [
        {"env_var_name": "WORKLOAD_NAME", "value": "devops-monitoring"},
        {
            "env_var_name": "CODE_REPOSITORY_NAME",
            "value": "geekcafe/geek-cafe-devops-monitoring",
            "mode_gated": True,
        },
    ]
    scripted = ScriptedInput(["", ""])

    result = cmd.prompt_and_write_env_file("prod", parameters, input_func=scripted)

    assert result is not None
    loaded = cmd.load_env_file(".env.prod")
    # mode_gated param IS prompted/written when mode is None.
    assert loaded["CODE_REPOSITORY_NAME"] == "geekcafe/geek-cafe-devops-monitoring"
    assert "CODE_REPOSITORY_NAME" in "".join(scripted.prompts)


# ---------------------------------------------------------------------------
# Mode-first prompting: _add_environment_interactive end-to-end (stubbed)
# ---------------------------------------------------------------------------


def _write_mode_config_json(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"cdk": {"parameters": _mode_parameters()}}), encoding="utf-8"
    )


def test_add_environment_interactive_stack_mode(tmp_path, monkeypatch):
    _clear_mode_env(monkeypatch)
    _write_mode_config_json(tmp_path)
    cmd = _command(tmp_path)

    monkeypatch.setattr(dc_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cmd, "select_deployment_mode", lambda default=None: "stack")
    # env name, then Enter-accept for the four prompted (non-gated/derived) params.
    answers = iter(["prod", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd._add_environment_interactive()

    loaded = cmd.load_env_file(".env.prod")
    assert "CODE_REPOSITORY_NAME" not in loaded
    assert "CODE_REPOSITORY_ARN" not in loaded
    assert loaded["DEPLOYMENT_MODE"] == "stack"
    assert loaded["PIPELINE_ENABLED"] == "false"
    assert loaded["STACK_ENABLED"] == "true"


def test_add_environment_interactive_pipeline_mode(tmp_path, monkeypatch):
    _clear_mode_env(monkeypatch)
    _write_mode_config_json(tmp_path)
    cmd = _command(tmp_path)

    monkeypatch.setattr(dc_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cmd, "select_deployment_mode", lambda default=None: "pipeline")
    # env name, then Enter-accept for six prompted params (includes two repo vars).
    answers = iter(["prod", "", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd._add_environment_interactive()

    loaded = cmd.load_env_file(".env.prod")
    assert loaded["CODE_REPOSITORY_NAME"] == "geekcafe/geek-cafe-devops-monitoring"
    assert loaded["CODE_REPOSITORY_ARN"] == "arn:aws:codeconnections:..."
    assert loaded["DEPLOYMENT_MODE"] == "pipeline"
    assert loaded["PIPELINE_ENABLED"] == "true"
    assert loaded["STACK_ENABLED"] == "false"
